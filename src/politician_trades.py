import requests
import json
from datetime import datetime, timedelta
from typing import List, Dict
import time
import re
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class PoliticianTradeTracker:
    def __init__(self):
        self.seen_trades_file = "data/seen_politician_trades.json"
        self.seen_trades = self._load_seen_trades()

        # Create session with retry strategy
        self.session = self._create_session()

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'max-age=0',
        }

        # Congressional/political figure company names to watch
        self.political_keywords = [
            'trump', 'biden', 'harris', 'pence', 'pelosi', 'mccarthy', 'schumer', 'mcconnell',
            'marjorie taylor greene', 'aoc', 'alexandria ocasio-cortez', 'matt gaetz', 'jim jordan',
            'ilhan omar', 'rashida tlaib', 'sen.', 'rep.', 'representative', 'senator', 'congress',
            'congressional', 'house of representatives', 'trust for', 'foundation'
        ]

    def _create_session(self):
        """Create requests session with retry strategy"""
        session = requests.Session()

        # Retry strategy: exponential backoff
        retry_strategy = Retry(
            total=3,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    def _load_seen_trades(self) -> set:
        try:
            with open(self.seen_trades_file, 'r') as f:
                return set(json.load(f))
        except FileNotFoundError:
            return set()

    def _save_seen_trades(self):
        import os
        os.makedirs('data', exist_ok=True)
        with open(self.seen_trades_file, 'w') as f:
            json.dump(list(self.seen_trades), f)

    def get_recent_trades(self) -> List[Dict]:
        """Fetch Congress trades from SEC using multiple methods"""
        trades = []

        print("[DEBUG] Attempting to fetch Congress trades from SEC...")

        # Try multiple SEC access methods
        sec_trades = self._try_sec_filing_index()
        if sec_trades:
            print(f"[DEBUG] Found {len(sec_trades)} trades via filing index")
            trades.extend(sec_trades)

        if not trades:
            sec_trades = self._try_sec_rss_atom()
            if sec_trades:
                print(f"[DEBUG] Found {len(sec_trades)} trades via RSS/Atom")
                trades.extend(sec_trades)

        if not trades:
            print("[DEBUG] SEC access failed, falling back to Google News...")
            trades = self._fetch_google_news_congress_trades()
            print(f"[DEBUG] Found {len(trades)} trades via Google News")

        self._save_seen_trades()
        return trades[:20]

    def _try_sec_filing_index(self) -> List[Dict]:
        """Try to access SEC filing index with retry logic"""
        trades = []

        try:
            today = datetime.now()
            yesterday = today - timedelta(days=1)
            dates_to_check = [today, yesterday]

            for date in dates_to_check:
                date_str = date.strftime('%Y%m%d')
                print(f"[DEBUG] Trying SEC filing index for {date_str}...")

                # Try multiple URL patterns
                urls = [
                    f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=4&dateb={date_str}&owner=exclude&count=100&output=atom",
                    f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=4&dateb={date_str}&owner=exclude&count=100",
                    f"https://www.sec.gov/edgar/browse/?type=4&dateb={date_str}",
                ]

                for url in urls:
                    try:
                        print(f"[DEBUG] Trying URL: {url[:80]}")
                        response = self.session.get(url, headers=self.headers, timeout=20)

                        print(f"[DEBUG] Got {response.status_code} response")

                        if response.status_code == 200:
                            from bs4 import BeautifulSoup
                            soup = BeautifulSoup(response.content, 'html.parser')

                            table = soup.find('table', {'class': ['tableFile', 'sgTable']})
                            if table:
                                rows = table.find_all('tr')[1:]
                                print(f"[DEBUG] Found {len(rows)} rows in table")

                                for row in rows[:40]:
                                    try:
                                        cols = row.find_all('td')
                                        if len(cols) < 4:
                                            continue

                                        company_name = cols[0].text.strip()

                                        if any(kw in company_name.lower() for kw in self.political_keywords):
                                            print(f"[DEBUG] Found political: {company_name}")
                                            cik = cols[1].text.strip()
                                            filing_date = cols[3].text.strip() if len(cols) > 3 else ''

                                            trade_id = f"sec_{cik}_{filing_date}"
                                            if trade_id not in self.seen_trades:
                                                trades.append({
                                                    'politician_name': company_name[:60],
                                                    'ticker': 'TBD',
                                                    'transaction_type': 'Form 4 Filing',
                                                    'amount': 'See SEC',
                                                    'transaction_date': filing_date,
                                                    'summary': f'Form 4: {company_name}',
                                                    'id': trade_id,
                                                    'source': 'SEC Form 4'
                                                })
                                                self.seen_trades.add(trade_id)
                                                print(f"[DEBUG] ✅ Added: {company_name}")
                                    except Exception as e:
                                        continue

                                if trades:
                                    return trades

                        time.sleep(2)  # Respect rate limits

                    except Exception as e:
                        print(f"[DEBUG] Error with URL {url[:60]}: {e}")
                        time.sleep(2)
                        continue

        except Exception as e:
            print(f"[DEBUG] Error in _try_sec_filing_index: {e}")

        return trades

    def _try_sec_rss_atom(self) -> List[Dict]:
        """Try SEC RSS/Atom feeds"""
        trades = []

        try:
            print("[DEBUG] Trying SEC RSS/Atom feeds...")
            rss_urls = [
                "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=4&owner=exclude&count=100&format=atom",
                "https://www.sec.gov/feeds/form-4",
            ]

            for url in rss_urls:
                try:
                    print(f"[DEBUG] Fetching {url[:60]}")
                    response = self.session.get(url, headers=self.headers, timeout=20)

                    print(f"[DEBUG] Got {response.status_code}")

                    if response.status_code == 200:
                        from xml.etree import ElementTree as ET
                        root = ET.fromstring(response.content)

                        namespaces = {'atom': 'http://www.w3.org/2005/Atom'}
                        entries = root.findall('atom:entry', namespaces)

                        print(f"[DEBUG] Found {len(entries)} entries")

                        for entry in entries[:30]:
                            try:
                                title = entry.find('atom:title', namespaces)
                                if title is not None and title.text:
                                    title_text = title.text
                                    if any(kw in title_text.lower() for kw in self.political_keywords):
                                        print(f"[DEBUG] Found: {title_text[:50]}")
                                        trades.append({
                                            'politician_name': title_text[:60],
                                            'ticker': 'TBD',
                                            'transaction_type': 'Form 4',
                                            'amount': 'See SEC',
                                            'transaction_date': datetime.now().strftime('%Y-%m-%d'),
                                            'summary': title_text[:80],
                                            'id': f"rss_{title_text}",
                                            'source': 'SEC Atom'
                                        })
                            except Exception as e:
                                continue

                        if trades:
                            return trades

                    time.sleep(2)

                except Exception as e:
                    print(f"[DEBUG] Error with RSS {url[:60]}: {e}")
                    time.sleep(2)

        except Exception as e:
            print(f"[DEBUG] Error in _try_sec_rss_atom: {e}")

        return trades

    def _fetch_google_news_congress_trades(self) -> List[Dict]:
        """Fallback to Google News if SEC fails"""
        trades = []

        try:
            from xml.etree import ElementTree as ET

            query = 'Congress stock trading'
            rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

            print(f"[DEBUG] Fetching Google News for: {query}")
            response = requests.get(rss_url, headers=self.headers, timeout=15)

            if response.status_code == 200:
                root = ET.fromstring(response.content)
                items = root.findall('.//item')

                print(f"[DEBUG] Found {len(items)} Google News items")

                for item in items[:15]:
                    try:
                        title = item.find('title')
                        if title is not None and title.text:
                            title_text = title.text
                            trade_id = f"gnews_{title_text}"

                            if trade_id not in self.seen_trades:
                                trades.append({
                                    'politician_name': 'Congress Member',
                                    'ticker': 'TBD',
                                    'transaction_type': 'News Report',
                                    'amount': 'See Article',
                                    'transaction_date': datetime.now().strftime('%Y-%m-%d'),
                                    'summary': title_text[:80],
                                    'id': trade_id,
                                    'source': 'Google News'
                                })
                                self.seen_trades.add(trade_id)
                                print(f"[DEBUG] Added: {title_text[:50]}")

                    except Exception as e:
                        continue

        except Exception as e:
            print(f"[DEBUG] Error fetching Google News fallback: {e}")

        return trades

    def format_trade_alert(self, trade: Dict) -> str:
        """Format a trade into readable alert text"""
        politician = trade.get('politician_name', 'Unknown')
        ticker = trade.get('ticker', 'N/A')
        action = trade.get('transaction_type', 'Trade')
        date = trade.get('transaction_date', 'Unknown')
        source = trade.get('source', 'SEC')

        alert = f"📊 CONGRESSIONAL TRADE\n{politician}\n{action} {ticker}\nDate: {date}\nSource: {source}"
        if trade.get('summary'):
            alert += f"\n{trade['summary'][:60]}"
        alert += "\n---"

        return alert
