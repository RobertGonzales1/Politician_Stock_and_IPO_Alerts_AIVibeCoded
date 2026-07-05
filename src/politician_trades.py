import requests
import json
import re
import time
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Congressional STOCK Act disclosures (Periodic Transaction Reports) parsed to JSON.
# This mirrors the official filings at disclosures-clerk.house.gov. Members of
# Congress do NOT file SEC Form 4s, so House Clerk PTR data is the authoritative
# source for politician trades. Verified live 2026-07-05 (updated through 2026-07-04).
HOUSE_TRANSACTIONS_URL = "https://raw.githubusercontent.com/TattooedHead/house-stock-watcher-data/main/data/all_transactions.json"

# Senate trades come straight from the official eFD system (efdsearch.senate.gov):
# accept the usage agreement to get a session, query the PTR search API, then
# parse each electronic filing's transaction table. Flow and response structure
# verified live 2026-07-05. Paper (scanned) filings can't be parsed and are skipped.
SENATE_EFD_LANDING = "https://efdsearch.senate.gov/search/home/"
SENATE_EFD_SEARCH = "https://efdsearch.senate.gov/search/"
SENATE_EFD_REPORTS_API = "https://efdsearch.senate.gov/search/report/data/"
SENATE_MAX_REPORTS_PER_RUN = 20

# Alert on trades disclosed within this many days (STOCK Act allows up to 45 days
# between trade and disclosure, so the disclosure date is what makes a trade "news").
DISCLOSURE_WINDOW_DAYS = 14
MAX_ALERTS = 50


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

        print("[DEBUG] Fetching Senate PTR disclosures (official eFD system)...")
        senate = self._fetch_senate_trades()
        print(f"[DEBUG] Senate: {len(senate)} trades disclosed in last {DISCLOSURE_WINDOW_DAYS} days")
        candidates.extend(senate)

        print("[DEBUG] Fetching Google News (supplementary, ticker-bearing articles only)...")
        news = self._fetch_google_news_trades()
        print(f"[DEBUG] Google News: {len(news)} trades with tickers")
        candidates.extend(news)

        # Drop already-alerted trades (and same-run duplicates).
        fresh = []
        run_ids = set()
        for t in candidates:
            if t['id'] in self.seen_trades or t['id'] in run_ids:
                continue
            run_ids.add(t['id'])
            fresh.append(t)

        # Interleave across politicians so one filer disclosing dozens of
        # trades at once doesn't crowd everyone else out of a capped email.
        by_politician = {}
        for t in fresh:
            by_politician.setdefault(t['politician_name'], []).append(t)
        new_trades = []
        while len(new_trades) < MAX_ALERTS and any(by_politician.values()):
            for items in by_politician.values():
                if items:
                    new_trades.append(items.pop(0))
                    if len(new_trades) >= MAX_ALERTS:
                        break

        # Only mark the trades we actually send as seen — anything over the
        # cap goes out in a later run instead of being dropped silently.
        for t in new_trades:
            self.seen_trades.add(t['id'])

        # A Senate filing is only marked fully processed once every one of its
        # trades has been sent, so over-cap leftovers still go out next run.
        filing_trade_ids = {}
        for t in candidates:
            marker = t.get('filing_marker')
            if marker:
                filing_trade_ids.setdefault(marker, []).append(t['id'])
        for marker, ids in filing_trade_ids.items():
            if all(i in self.seen_trades for i in ids):
                self.seen_trades.add(marker)

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
                        'owner': owner,
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

    def _fetch_senate_trades(self) -> List[Dict]:
        """Scrape Senate PTRs from the official eFD system.

        Verified flow: GET the landing page for a CSRF form token, POST the
        usage-agreement to obtain a session, then POST the search API for
        Periodic Transaction Reports (report type 11) submitted in our window.
        Each electronic filing page holds a 9-column transaction table:
        [#, tx date, owner, ticker, asset name, asset type, type, amount, comment].
        """
        trades = []
        try:
            # Step 1: accept the usage agreement to get a session
            landing = self.session.get(SENATE_EFD_LANDING, headers=self.headers, timeout=30)
            soup = BeautifulSoup(landing.text, 'html.parser')
            csrf_input = soup.find(attrs={'name': 'csrfmiddlewaretoken'})
            form_token = csrf_input.get('value') if csrf_input else None
            if not form_token:
                print("[WARN] Senate eFD: agreement page has no usable CSRF token — "
                      "site changed or blocked this runner, source needs attention!")
                return trades
            self.session.post(
                SENATE_EFD_LANDING,
                data={'csrfmiddlewaretoken': form_token, 'prohibition_agreement': '1'},
                headers={**self.headers, 'Referer': SENATE_EFD_LANDING},
                timeout=30,
            )
            csrftoken = self.session.cookies.get('csrftoken') or self.session.cookies.get('csrf')
            if not csrftoken:
                print("[WARN] Senate eFD: no CSRF cookie after agreement — likely "
                      "blocked, source needs attention!")
                return trades

            # Step 2: search for PTRs submitted within the window
            start_date = (datetime.now() - timedelta(days=DISCLOSURE_WINDOW_DAYS)).strftime('%m/%d/%Y 00:00:00')
            payload = {
                'start': '0',
                'length': '100',
                'report_types': '[11]',
                'filer_types': '[]',
                'submitted_start_date': start_date,
                'submitted_end_date': '',
                'candidate_state': '',
                'senator_state': '',
                'office_id': '',
                'first_name': '',
                'last_name': '',
                'csrfmiddlewaretoken': csrftoken,
            }
            resp = self.session.post(
                SENATE_EFD_REPORTS_API,
                data=payload,
                headers={**self.headers, 'Referer': SENATE_EFD_SEARCH},
                timeout=30,
            )
            if resp.status_code != 200:
                print(f"[WARN] Senate eFD: search API returned HTTP {resp.status_code}, "
                      f"source needs attention!")
                return trades
            body = resp.json()
            rows = body.get('data') if isinstance(body, dict) else None
            if not isinstance(rows, list):
                print("[WARN] Senate eFD: search API returned an unexpected JSON "
                      "shape — source needs attention!")
                return trades
            print(f"[DEBUG] Senate eFD: {len(rows)} PTR filings in window")

            # Step 3: parse each electronic filing's transaction table
            fetched = 0
            parsed_ok = 0
            for row in rows:
                try:
                    # Verified row shape: [first, last, "Name (Senator)", link_html, date_received]
                    if len(row) < 5:
                        continue
                    first, last, _display, link_html, date_received = row[:5]
                    a = BeautifulSoup(link_html, 'html.parser').find('a')
                    href = a.get('href', '') if a else ''
                    name = f"Sen. {first.strip()} {last.strip(' ,')}"

                    if '/search/view/ptr/' not in href:
                        print(f"[DEBUG] Senate eFD: skipping paper filing by {name}")
                        continue
                    # Skip filings whose every trade already went out — don't
                    # spend the per-run fetch cap re-downloading them.
                    filing_marker = f"senate_filing_{href}"
                    if filing_marker in self.seen_trades:
                        continue
                    if fetched >= SENATE_MAX_REPORTS_PER_RUN:
                        print("[DEBUG] Senate eFD: report cap reached, rest next run")
                        break
                    fetched += 1

                    time.sleep(1)  # be polite to the Senate's servers
                    page = self.session.get('https://efdsearch.senate.gov' + href,
                                            headers=self.headers, timeout=30)
                    if page.status_code != 200:
                        print(f"[DEBUG] Senate eFD: filing page HTTP {page.status_code} for {name}")
                        continue
                    tbody = BeautifulSoup(page.text, 'html.parser').find('tbody')
                    if tbody is None:
                        print(f"[DEBUG] Senate eFD: no transaction table for {name}")
                        continue
                    parsed_ok += 1

                    filing_trade_count = 0
                    for tr in tbody.find_all('tr'):
                        cols = [td.get_text(strip=True) for td in tr.find_all('td')]
                        if len(cols) < 8:
                            continue
                        tx_num, tx_date, owner, ticker, _asset, _atype, tx_type, amount = cols[:8]
                        if not ticker or ticker.upper() in ('--', 'N/A', 'NA', '-', 'NONE'):
                            continue
                        filing_trade_count += 1
                        trades.append({
                            'id': f"senate_{href}_{tx_num}",
                            'politician_name': name,
                            'ticker': ticker,
                            'transaction_type': self._map_transaction_type(tx_type),
                            'amount': amount,
                            'owner': owner,
                            'transaction_date': tx_date,
                            'disclosure_date': date_received,
                            'source': 'Senate PTR',
                            'link': '',
                            'filing_marker': filing_marker,
                        })

                    if filing_trade_count == 0:
                        # Nothing alertable in this filing (bonds, options with no
                        # ticker, etc.) — mark it done so it isn't re-fetched daily.
                        self.seen_trades.add(filing_marker)
                except Exception as e:
                    print(f"[DEBUG] Senate eFD: skipping malformed filing: {str(e)[:60]}")
                    continue

            if fetched and not parsed_ok:
                print("[WARN] Senate eFD: filings fetched but none parsed — page "
                      "template may have changed, source needs attention!")

        except requests.RequestException as e:
            print(f"[WARN] Senate eFD: request failed — {str(e)[:80]}")
        except ValueError as e:
            print(f"[WARN] Senate eFD: bad JSON from search API — {str(e)[:80]}")
        except Exception as e:
            # Backstop: a Senate failure must never take down the other sources.
            print(f"[WARN] Senate eFD: unexpected error — {str(e)[:80]}")

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

        # Show the account owner (Spouse, Joint, Child) when it isn't the member
        # themselves — filings often list several same-day lots split by account.
        owner = (trade.get('owner') or '').strip()
        detail = amount
        if owner and owner.lower() not in ('self', '--', 'n/a'):
            detail = f"{amount}, {owner}" if amount else owner

        lines = [name, f"{action} {ticker}" + (f"  ({detail})" if detail else "")]
        date_parts = []
        if traded:
            date_parts.append(f"Traded: {traded}")
        if disclosed:
            date_parts.append(f"Disclosed: {disclosed}")
        if date_parts:
            lines.append(" | ".join(date_parts))
        if trade.get('summary'):
            lines.append(trade['summary'])
        if source:
            lines.append(f"Source: {source}")
        lines.append('---')
        return "\n".join(lines)
