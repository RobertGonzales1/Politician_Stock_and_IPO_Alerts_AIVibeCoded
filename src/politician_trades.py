import requests
import json
import re
import time
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Congressional STOCK Act disclosures (Periodic Transaction Reports) parsed to JSON.
# This mirrors the official filings at disclosures-clerk.house.gov. Members of
# Congress do NOT file SEC Form 4s, so House Clerk PTR data is the authoritative
# source for politician trades. Verified live 2026-07-05 (updated through 2026-07-04).
# NOTE: no maintained free Senate equivalent exists (senate-stock-watcher died in
# 2020 and its records lack disclosure_date entirely), so Senate trades are only
# covered via the news feed below.
HOUSE_TRANSACTIONS_URL = "https://raw.githubusercontent.com/TattooedHead/house-stock-watcher-data/main/data/all_transactions.json"

# Alert on trades disclosed within this many days (STOCK Act allows up to 45 days
# between trade and disclosure, so the disclosure date is what makes a trade "news").
DISCLOSURE_WINDOW_DAYS = 14
MAX_ALERTS = 25


class PoliticianTradeTracker:
    def __init__(self):
        self.seen_trades_file = "data/seen_politician_trades.json"
        self.seen_trades = self._load_seen_trades()
        self.session = self._create_session()
        self.headers = {
            'User-Agent': 'PoliticianStockAlerts/1.0 (rvg2151@gmail.com)',
        }

    def _create_session(self):
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def _load_seen_trades(self) -> set:
        try:
            with open(self.seen_trades_file, 'r') as f:
                data = json.load(f)
                return set(data) if isinstance(data, list) else set()
        except (FileNotFoundError, ValueError):
            # Missing or corrupted file (e.g. interrupted CI write) — start fresh
            # rather than crashing every future run.
            return set()

    def _save_seen_trades(self):
        import os
        os.makedirs('data', exist_ok=True)
        with open(self.seen_trades_file, 'w') as f:
            json.dump(list(self.seen_trades), f)

    def get_recent_trades(self) -> List[Dict]:
        """Collect politician trades from official disclosure data + news, newest first."""
        candidates = []

        print("[DEBUG] === FETCHING CONGRESS TRADES ===")

        print("[DEBUG] Fetching House PTR disclosures (official House Clerk data)...")
        house = self._fetch_disclosures(HOUSE_TRANSACTIONS_URL, 'House PTR')
        print(f"[DEBUG] House: {len(house)} trades disclosed in last {DISCLOSURE_WINDOW_DAYS} days")
        candidates.extend(house)

        print("[DEBUG] Fetching Google News (supplementary, ticker-bearing articles only)...")
        news = self._fetch_google_news_trades()
        print(f"[DEBUG] Google News: {len(news)} trades with tickers")
        candidates.extend(news)

        # Drop already-alerted trades (and same-run duplicates), cap the email
        # size, and only mark the trades we actually send as seen — so anything
        # over the cap is sent in a later run instead of dropped silently.
        new_trades = []
        run_ids = set()
        for t in candidates:
            if t['id'] in self.seen_trades or t['id'] in run_ids:
                continue
            run_ids.add(t['id'])
            new_trades.append(t)
            if len(new_trades) >= MAX_ALERTS:
                break
        for t in new_trades:
            self.seen_trades.add(t['id'])
        self._save_seen_trades()

        print(f"[DEBUG] {len(new_trades)} new trades after dedup (cap {MAX_ALERTS})")
        return new_trades

    def _fetch_disclosures(self, url: str, source_label: str) -> List[Dict]:
        """Download a PTR transactions dataset and return recently disclosed trades."""
        trades = []
        try:
            resp = self.session.get(url, headers=self.headers, timeout=120)
            if resp.status_code != 200:
                print(f"[DEBUG] {source_label} dataset returned HTTP {resp.status_code}")
                return trades

            records = resp.json()
            if not isinstance(records, list):
                print(f"[DEBUG] {source_label} dataset has unexpected shape")
                return trades
            print(f"[DEBUG] {source_label} dataset: {len(records)} total transactions")

            cutoff = datetime.now().date() - timedelta(days=DISCLOSURE_WINDOW_DAYS)
            newest_disclosed = None

            for rec in records:
                try:
                    disclosed = self._parse_date(rec.get('disclosure_date', ''))
                    if disclosed and (newest_disclosed is None or disclosed > newest_disclosed):
                        newest_disclosed = disclosed
                    if disclosed is None or disclosed < cutoff:
                        continue

                    ticker = (rec.get('ticker') or '').strip()
                    if not ticker or ticker.upper() in ('--', 'N/A', 'NA', '-', 'NONE'):
                        continue

                    name = rec.get('representative') or rec.get('senator') or 'Unknown'
                    district = (rec.get('district') or '').strip()
                    if district:
                        name = f"{name} ({district})"

                    tx_type_raw = rec.get('type', '')
                    action = self._map_transaction_type(tx_type_raw)
                    traded = rec.get('transaction_date', '')
                    amount = rec.get('amount', '')
                    owner = rec.get('owner', '')

                    trade_id = "ptr_{}_{}_{}_{}_{}_{}".format(
                        rec.get('filing_id') or rec.get('ptr_link') or name,
                        ticker, traded, tx_type_raw, owner, amount)

                    trades.append({
                        'id': trade_id,
                        'politician_name': name,
                        'ticker': ticker,
                        'transaction_type': action,
                        'amount': amount,
                        'transaction_date': traded,
                        'disclosure_date': rec.get('disclosure_date', ''),
                        'source': source_label,
                        'link': rec.get('source_url') or rec.get('ptr_link') or '',
                    })
                except Exception as e:
                    print(f"[DEBUG] Skipping malformed {source_label} record: {str(e)[:60]}")
                    continue

            # A dead/stale source must be loud in the logs, not look like a quiet week.
            if not trades:
                if newest_disclosed is None:
                    print(f"[WARN] {source_label}: no parseable disclosure dates — the "
                          f"dataset schema may have changed, source needs attention!")
                elif newest_disclosed < cutoff:
                    print(f"[WARN] {source_label}: dataset looks STALE — newest "
                          f"disclosure is {newest_disclosed}, source needs attention!")

            # Newest disclosures first
            trades.sort(key=lambda t: self._parse_date(t['disclosure_date']) or cutoff, reverse=True)

        except requests.RequestException as e:
            print(f"[DEBUG] Error fetching {source_label}: {str(e)[:80]}")
        except ValueError as e:
            print(f"[DEBUG] Error parsing {source_label} JSON: {str(e)[:80]}")

        return trades

    def _parse_date(self, value: str) -> Optional[date]:
        """Parse dates that appear as MM/DD/YYYY or YYYY-MM-DD."""
        if not value:
            return None
        for fmt in ('%m/%d/%Y', '%Y-%m-%d'):
            try:
                return datetime.strptime(value.strip(), fmt).date()
            except ValueError:
                continue
        return None

    def _map_transaction_type(self, tx_type: str) -> str:
        t = (tx_type or '').lower()
        if 'purchase' in t or 'buy' in t or 'bought' in t:
            return 'BUY 📈'
        if 'sale' in t or 'sell' in t or 'sold' in t:
            return 'SELL 📉'
        if 'exchange' in t:
            return 'EXCHANGE 🔄'
        return 'TRADE 📊'

    def _fetch_google_news_trades(self) -> List[Dict]:
        """Supplementary: Congress trading news that names a specific ticker."""
        trades = []
        try:
            from xml.etree import ElementTree as ET

            query = 'Congress stock trading'
            rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
            response = self.session.get(rss_url, headers=self.headers, timeout=15)

            if response.status_code != 200:
                print(f"[DEBUG] Google News returned HTTP {response.status_code}")
                return trades

            root = ET.fromstring(response.content)
            items = root.findall('.//item')
            print(f"[DEBUG] Google News: {len(items)} articles")

            for item in items[:30]:
                try:
                    title_elem = item.find('title')
                    if title_elem is None or not title_elem.text:
                        continue
                    title = title_elem.text
                    desc_elem = item.find('description')
                    description = desc_elem.text if desc_elem is not None and desc_elem.text else ''
                    combined = f"{title} {description}"

                    # Only alert when the article names a specific ticker —
                    # policy/debate articles without tickers are noise.
                    ticker = self._extract_ticker_from_news(combined)
                    if not ticker:
                        continue

                    action = self._map_transaction_type(combined)
                    politician = self._extract_politician_from_news(title)

                    # ID excludes the date so the same headline never re-alerts.
                    trade_id = f"gnews_{title[:80]}"

                    trades.append({
                        'id': trade_id,
                        'politician_name': politician,
                        'ticker': ticker,
                        'transaction_type': action,
                        'amount': '',
                        # Article date is when it was reported, not when the trade
                        # happened — leave trade dates blank rather than fabricating.
                        'transaction_date': '',
                        'disclosure_date': '',
                        'source': 'Google News',
                        'link': '',
                        'summary': title[:100],
                    })
                except Exception:
                    continue

        except Exception as e:
            print(f"[DEBUG] Error fetching Google News: {str(e)[:80]}")

        return trades

    def _extract_ticker_from_news(self, text: str) -> Optional[str]:
        """Find an explicit ticker like $NVDA or (NVDA) in article text."""
        match = re.search(r'\$([A-Z]{1,5})\b', text)
        if match:
            return match.group(1)
        match = re.search(r'\(([A-Z]{2,5})\)', text)
        if match and match.group(1) not in ('CEO', 'CFO', 'GOP', 'USA', 'SEC', 'FBI', 'CIA', 'IRS', 'ETF', 'IPO', 'AI', 'TV', 'PAC', 'DOJ', 'NYSE'):
            return match.group(1)
        return None

    def _extract_politician_from_news(self, title: str) -> str:
        politicians = [
            'pelosi', 'trump', 'biden', 'harris', 'ossoff', 'hawley', 'johnson',
            'kean', 'gaetz', 'jordan', 'schumer', 'mcconnell', 'mccarthy', 'fetterman',
            'vance', 'omar', 'tlaib', 'greene', 'ocasio-cortez', 'aoc', 'pappas',
            'goodlander', 'krishnamoorthi', 'cloud', 'garcia', 'young', 'mullin',
            'britt', 'hickenlooper', 'wexton', 'doggett', 'jayapal',
        ]
        title_lower = title.lower()
        for politician in politicians:
            if politician in title_lower:
                return politician.replace('-', ' ').title()

        match = re.search(r'(?:Rep|Representative|Sen|Senator)\.?\s+([A-Z]\w+(?:\s+[A-Z]\w+)?)', title)
        if match:
            return match.group(1).strip()

        return "Congress Member"

    def format_trade_alert(self, trade: Dict) -> str:
        """Format one trade for the alert email."""
        name = trade.get('politician_name', 'Unknown')
        action = trade.get('transaction_type', 'TRADE 📊')
        ticker = trade.get('ticker', 'N/A')
        amount = trade.get('amount', '')
        traded = trade.get('transaction_date', '')
        disclosed = trade.get('disclosure_date', '')
        source = trade.get('source', '')

        lines = [name, f"{action} {ticker}" + (f"  ({amount})" if amount else "")]
        date_line = f"Traded: {traded}" if traded else ""
        if disclosed:
            date_line += f" | Disclosed: {disclosed}"
        if date_line:
            lines.append(date_line)
        if trade.get('summary'):
            lines.append(trade['summary'])
        if source:
            lines.append(f"Source: {source}")
        lines.append('---')
        return "\n".join(lines)
