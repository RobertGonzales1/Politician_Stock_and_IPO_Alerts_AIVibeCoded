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
        self.session = self._create_session()

        # SEC requires proper User-Agent
        self.headers = {
            'User-Agent': 'PoliticianStockAlerts/1.0 (rvg2151@gmail.com)',
            'Accept': 'application/json',
        }

        # Known Congressional member CIKs (looked up from SEC.gov)
        self.congressional_ciks = {
            # Senators and House Members with known SEC filings
            '0001763161': 'Pelosi, Peggie',
            '0001470019': 'Pelosi, Paul Francis Jr',
            '0001628233': 'Kelly, Mark',
            '0001802538': 'Hawley, Josh',
            '0001710340': 'Ossoff, Jon',
            '0001903126': 'Fetterman, John',
            '0001777414': 'Vance, JD',
            '0001864071': 'Trump, Donald J',
            '0001565280': 'McHenry, Patrick',
            '0001768015': 'Kean, Thomas H',
            '0001829174': 'Goodlander, Kristin D',
            '0001916214': 'Krishnamoorthi, Raja',
            '0001772548': 'Johnson, Mike',
            '0001767192': 'Bresnahan, Kyle',
            '0001848695': 'Pappas, Chris',
            '0001893149': 'Young, Don',
            '0001830264': 'Garcia, Robert',
            '0001812180': 'Cloud, Al',
            '0001865523': 'Tlaib, Rashida',
            '0001841717': 'Omar, Ilhan',
            '0001768567': 'Gaetz, Matt',
            '0001902131': 'Jordan, Jim',
            '0001639109': 'Schumer, Chuck',
            '0001398087': 'McConnell, Mitch',
            '0001534474': 'McCarthy, Kevin',
            '0001755260': 'Greene, Marjorie Taylor',
            '0001907022': 'Ocasio-Cortez, Alexandria',
        }

    def _create_session(self):
        """Create requests session with retry strategy"""
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
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
        """Fetch Congress trades from SEC JSON API (official source) + Google News"""
        trades = []

        print("[DEBUG] === FETCHING CONGRESS TRADES ===")

        # Primary: SEC JSON API
        print("[DEBUG] Fetching from SEC data.sec.gov JSON API (primary)...")
        sec_trades = self._fetch_sec_json_api_trades()
        print(f"[DEBUG] Found {len(sec_trades)} trades from SEC API")
        trades.extend(sec_trades)

        # Supplementary: Google News
        print("[DEBUG] Fetching from Google News (supplementary)...")
        google_trades = self._fetch_google_news_trades()
        print(f"[DEBUG] Found {len(google_trades)} trades from Google News")
        trades.extend(google_trades)

        self._save_seen_trades()
        return trades[:20]

    def _fetch_sec_json_api_trades(self) -> List[Dict]:
        """Fetch Form 4 filings from SEC's official JSON API"""
        trades = []

        try:
            # Method 1: Query recent Form 4s
            print("[DEBUG] Querying SEC for recent Form 4 filings...")
            url = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=4&dateb=&owner=exclude&count=100&output=json"

            print(f"[DEBUG] Fetching: {url[:80]}")
            response = self.session.get(url, headers=self.headers, timeout=25)
            print(f"[DEBUG] SEC Response: {response.status_code}")

            if response.status_code == 200:
                try:
                    data = response.json()
                    # Handle both old and new SEC API formats
                    filings = data.get('filings', {}).get('filing', [])
                    if not filings:
                        filings = data.get('results', [])

                    print(f"[DEBUG] Found {len(filings)} Form 4 filings")

                    for filing in filings[:50]:
                        try:
                            company_name = filing.get('company_name', '') or filing.get('cikName', '')
                            cik = filing.get('cik_str', '') or filing.get('cik', '')
                            filing_date = filing.get('filing_date', '')

                            # Check if this matches Congressional patterns
                            if self._is_political_filing(company_name):
                                print(f"[DEBUG] ✓ Found political filing: {company_name}")

                                # Fetch detailed filing
                                details = self._fetch_form4_json_details(cik, filing_date)
                                if details:
                                    trades.append(details)
                                    self.seen_trades.add(details.get('id', ''))
                                    print(f"[DEBUG] ✅ ADDED: {company_name}")

                        except Exception as e:
                            print(f"[DEBUG] Error parsing filing: {str(e)[:60]}")
                            continue

                except (json.JSONDecodeError, ValueError) as e:
                    print(f"[DEBUG] Failed to parse SEC JSON: {str(e)[:60]}")

        except Exception as e:
            print(f"[DEBUG] Error fetching SEC JSON API: {str(e)[:80]}")

        # Method 2: Fallback - check known Congressional CIKs
        if not trades:
            print("[DEBUG] Trying known Congressional CIKs...")
            trades.extend(self._fetch_known_congressional_ciks())

        time.sleep(2)
        return trades

    def _is_political_filing(self, company_name: str) -> bool:
        """Check if company name indicates a Congressional member"""
        political_keywords = [
            'trust', 'foundation', 'pac', 'committee',
            'trump', 'biden', 'harris', 'pence', 'pelosi', 'mccarthy',
            'schumer', 'mcconnell', 'gaetz', 'jordan', 'omar', 'tlaib',
            'ossoff', 'fetterman', 'kean', 'vance', 'johnson',
            'goodlander', 'krishnamoorthi', 'pappas', 'bresnahan',
            'young', 'hawley', 'congressional', 'senate', 'house'
        ]
        return any(kw in company_name.lower() for kw in political_keywords)

    def _fetch_form4_json_details(self, cik: str, date: str) -> Dict:
        """Fetch Form 4 details from SEC JSON API"""
        try:
            # Use data.sec.gov for detailed submissions
            url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
            print(f"[DEBUG] Fetching Form 4 details from: {url[:70]}")

            response = self.session.get(url, headers=self.headers, timeout=20)

            if response.status_code == 200:
                data = response.json()
                company_name = data.get('cik_name', 'Unknown')
                filings = data.get('filings', {}).get('recent', {}).get('form', [])

                # Find Form 4 filings
                for i, form_type in enumerate(filings):
                    if form_type == '4':
                        filing_date = data.get('filings', {}).get('recent', {}).get('filingDate', [])[i]

                        if filing_date == date:
                            accession = data.get('filings', {}).get('recent', {}).get('accessionNumber', [])[i]

                            # Extract transaction details
                            transaction_type = self._extract_form4_transaction_type(data, i)
                            ticker = self._extract_ticker_from_form4(data, i)

                            return {
                                'politician_name': company_name[:70],
                                'ticker': ticker if ticker else 'TBD',
                                'transaction_type': transaction_type if transaction_type else 'TRADE 📊',
                                'amount': 'See SEC Filing',
                                'transaction_date': filing_date,
                                'summary': f'Form 4: {company_name}',
                                'id': f"sec_{cik}_{date}_{accession}",
                                'source': 'SEC Form 4 (JSON API)',
                                'link': f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik.lstrip('0')}&type=4&dateb=&owner=exclude&count=40"
                            }

        except Exception as e:
            print(f"[DEBUG] Error fetching Form 4 JSON details: {str(e)[:60]}")

        return None

    def _fetch_known_congressional_ciks(self) -> List[Dict]:
        """Fetch trades from known Congressional member CIKs"""
        trades = []

        for cik, name in self.congressional_ciks.items():
            try:
                print(f"[DEBUG] Checking {name} (CIK: {cik})")

                url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
                response = self.session.get(url, headers=self.headers, timeout=15)

                if response.status_code == 200:
                    data = response.json()
                    filings = data.get('filings', {}).get('recent', {})
                    forms = filings.get('form', [])

                    # Find recent Form 4s
                    for i, form in enumerate(forms[:20]):
                        if form == '4':
                            filing_date = filings.get('filingDate', [])[i]
                            trade_id = f"sec_{cik}_{filing_date}"

                            if trade_id not in self.seen_trades:
                                trades.append({
                                    'politician_name': name,
                                    'ticker': 'PENDING',
                                    'transaction_type': 'Form 4',
                                    'amount': 'See SEC',
                                    'transaction_date': filing_date,
                                    'summary': f'Form 4: {name}',
                                    'id': trade_id,
                                    'source': 'SEC Form 4 (API)',
                                    'link': f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=4"
                                })
                                self.seen_trades.add(trade_id)
                                print(f"[DEBUG] ✅ Added {name} Form 4")

                time.sleep(1)

            except Exception as e:
                print(f"[DEBUG] Error with {name}: {str(e)[:60]}")

        return trades

    def _extract_form4_transaction_type(self, data: Dict, index: int) -> str:
        """Extract transaction type from Form 4 data"""
        try:
            transactions = data.get('filings', {}).get('recent', {}).get('transactionType', [])
            if index < len(transactions):
                tx_type = transactions[index].lower()
                if 'purchase' in tx_type or 'open market buy' in tx_type:
                    return 'BUY 📈'
                elif 'sale' in tx_type or 'open market sell' in tx_type:
                    return 'SELL 📉'
        except:
            pass
        return None

    def _extract_ticker_from_form4(self, data: Dict, index: int) -> str:
        """Extract ticker symbol from Form 4 data"""
        try:
            tickers = data.get('filings', {}).get('recent', {}).get('ticker', [])
            if index < len(tickers):
                return tickers[index]
        except:
            pass
        return None

    def _fetch_google_news_trades(self) -> List[Dict]:
        """Fetch Congress trades from Google News (supplementary source)"""
        trades = []

        try:
            from xml.etree import ElementTree as ET

            query = 'Congress stock trading'
            rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

            print(f"[DEBUG] Fetching Google News: {query}")
            response = requests.get(rss_url, headers={'User-Agent': self.headers['User-Agent']}, timeout=15)

            if response.status_code == 200:
                root = ET.fromstring(response.content)
                items = root.findall('.//item')
                print(f"[DEBUG] Found {len(items)} Google News items")

                for item in items[:15]:
                    try:
                        title_elem = item.find('title')
                        link_elem = item.find('link')

                        if title_elem is None or not title_elem.text:
                            continue

                        title = title_elem.text
                        link = link_elem.text if link_elem is not None else ''
                        trade_id = f"gnews_{title}_{datetime.now().date()}"

                        if trade_id not in self.seen_trades:
                            trades.append({
                                'politician_name': 'Congress Member',
                                'ticker': 'TBD',
                                'transaction_type': 'TRADE 📊',
                                'amount': 'See Article',
                                'transaction_date': datetime.now().strftime('%Y-%m-%d'),
                                'summary': title[:80],
                                'id': trade_id,
                                'source': 'Google News',
                                'link': link
                            })
                            self.seen_trades.add(trade_id)
                            print(f"[DEBUG] Added Google News: {title[:60]}")

                    except Exception as e:
                        continue

        except Exception as e:
            print(f"[DEBUG] Error fetching Google News: {str(e)[:80]}")

        return trades

    def format_trade_alert(self, trade: Dict) -> str:
        """Format trade alert - simple format"""
        politician = trade.get('politician_name', 'Unknown')
        ticker = trade.get('ticker', 'TBD')
        action = trade.get('transaction_type', 'Trade')
        date = trade.get('transaction_date', 'Unknown')
        source = trade.get('source', 'Unknown')

        # Simple, clean format
        alert = f"{politician}\n{action} {ticker}\n{date}"
        alert += "\n---"

        return alert
