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

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'max-age=0',
            'Referer': 'https://www.sec.gov/',
        }

        # Congressional/political figure patterns
        self.political_keywords = [
            'trust', 'foundation', 'pac', 'committee',
            'trump', 'biden', 'harris', 'pence', 'pelosi', 'mccarthy', 'schumer', 'mcconnell',
            'gaetz', 'jordan', 'omar', 'tlaib', 'ossoff', 'fetterman', 'kean', 'vance',
            'johnson', 'goodlander', 'krishnamoorthi'
        ]

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
        """Fetch Congress trades from both SEC (primary) and Google News (supplementary)"""
        trades = []

        print("[DEBUG] === FETCHING CONGRESS TRADES ===")

        # Primary source: SEC Form 4 filings
        print("[DEBUG] Fetching from SEC Form 4 filings (primary)...")
        sec_trades = self._fetch_sec_form4_filings()
        print(f"[DEBUG] Found {len(sec_trades)} trades from SEC")
        trades.extend(sec_trades)

        # Supplementary source: Google News
        print("[DEBUG] Fetching from Google News (supplementary)...")
        google_trades = self._fetch_google_news_trades()
        print(f"[DEBUG] Found {len(google_trades)} trades from Google News")
        trades.extend(google_trades)

        self._save_seen_trades()
        return trades[:20]

    def _fetch_sec_form4_filings(self) -> List[Dict]:
        """Fetch Form 4 filings from SEC - primary method"""
        trades = []

        try:
            # Check last 3 days for filings
            dates_to_check = [datetime.now() - timedelta(days=i) for i in range(3)]

            for date in dates_to_check:
                date_str = date.strftime('%Y%m%d')
                print(f"\n[DEBUG] === Checking SEC Form 4 filings for {date_str} ===")

                # Primary SEC endpoint for Form 4 filings
                url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=4&dateb={date_str}&owner=exclude&count=100&search_text="

                try:
                    print(f"[DEBUG] Fetching from SEC: {url[:80]}")
                    response = self.session.get(url, headers=self.headers, timeout=25)
                    print(f"[DEBUG] SEC Response: {response.status_code}")

                    if response.status_code == 200:
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(response.content, 'html.parser')

                        # Find main results table
                        table = soup.find('table', {'class': 'tableFile'})

                        if table:
                            rows = table.find_all('tr')
                            print(f"[DEBUG] Found {len(rows)} rows in SEC table")

                            # Process each row
                            for row in rows[1:101]:  # Skip header, check up to 100 rows
                                try:
                                    cols = row.find_all('td')
                                    if len(cols) < 5:
                                        continue

                                    # Extract company info
                                    company_link = cols[0].find('a')
                                    if not company_link:
                                        continue

                                    company_name = company_link.text.strip()
                                    cik_link = cols[1].find('a')
                                    cik = cik_link.text.strip() if cik_link else ''
                                    filing_date = cols[3].text.strip() if len(cols) > 3 else ''

                                    # Check if this looks like a Congressional trade
                                    is_political = any(kw in company_name.lower() for kw in self.political_keywords)

                                    if is_political and company_name and cik and filing_date:
                                        print(f"[DEBUG] ✓ Found Congressional filing: {company_name}")

                                        trade_id = f"sec_{cik}_{filing_date}_{company_name}"

                                        if trade_id not in self.seen_trades:
                                            # Fetch full filing details
                                            filing_details = self._get_form4_details(cik, filing_date, company_name)

                                            if filing_details:
                                                trades.append(filing_details)
                                                self.seen_trades.add(trade_id)
                                                print(f"[DEBUG] ✅ ADDED: {company_name} - {filing_details.get('transaction_type', 'TRADE')} {filing_details.get('ticker', 'N/A')}")

                                except Exception as e:
                                    print(f"[DEBUG] Error parsing row: {str(e)[:60]}")
                                    continue

                        else:
                            print(f"[DEBUG] No table found in SEC response")

                    else:
                        print(f"[DEBUG] SEC returned {response.status_code}")

                except Exception as e:
                    print(f"[DEBUG] Error fetching SEC for {date_str}: {str(e)[:80]}")

                time.sleep(3)  # Respectful delay between requests

        except Exception as e:
            print(f"[DEBUG] Error in _fetch_sec_form4_filings: {str(e)[:100]}")

        return trades

    def _get_form4_details(self, cik: str, filing_date: str, company_name: str) -> Dict:
        """Get details from Form 4 filing"""
        try:
            print(f"[DEBUG] Fetching Form 4 details for CIK: {cik}")

            # Build URL to filing documents
            url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=4&dateb={filing_date}&owner=exclude&count=1"

            response = self.session.get(url, headers=self.headers, timeout=20)

            if response.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.content, 'html.parser')

                # Try to find the actual Form 4 document link
                doc_table = soup.find('table', {'class': 'tableFile'})
                if doc_table:
                    doc_link = doc_table.find('a', href=re.compile(r'\.htm'))
                    if doc_link:
                        doc_url = f"https://www.sec.gov{doc_link.get('href', '')}"
                        print(f"[DEBUG] Fetching Form 4 document")

                        doc_response = self.session.get(doc_url, headers=self.headers, timeout=15)
                        if doc_response.status_code == 200:
                            doc_text = doc_response.text.lower()

                            # Extract transaction info
                            ticker = self._extract_ticker_from_text(doc_text)
                            action = self._determine_action_from_text(doc_text)

                            if ticker and action:
                                return {
                                    'politician_name': company_name[:70],
                                    'ticker': ticker,
                                    'transaction_type': action,
                                    'amount': 'See SEC Filing',
                                    'transaction_date': filing_date,
                                    'summary': f'Form 4: {company_name}',
                                    'id': f"sec_{cik}_{filing_date}",
                                    'source': 'SEC Form 4',
                                    'link': doc_url
                                }

        except Exception as e:
            print(f"[DEBUG] Error getting Form 4 details: {str(e)[:60]}")

        # Return basic filing info if details fail
        return {
            'politician_name': company_name[:70],
            'ticker': 'PENDING',
            'transaction_type': 'Form 4 Filing',
            'amount': 'See SEC',
            'transaction_date': filing_date,
            'summary': f'Form 4: {company_name}',
            'id': f"sec_{cik}_{filing_date}",
            'source': 'SEC Form 4'
        }

    def _extract_ticker_from_text(self, text: str) -> str:
        """Extract ticker from Form 4 text"""
        # Look for $TICKER
        match = re.search(r'\$([A-Z]{1,5})\b', text)
        if match:
            return match.group(1)

        # Look for "Security: TICKER" or similar
        match = re.search(r'security[^:]*:\s*([A-Z]{1,5})\b', text)
        if match:
            return match.group(1)

        # Look for common symbols
        symbols = ['aapl', 'msft', 'googl', 'amzn', 'tsla', 'nvda', 'meta', 'nflx']
        for symbol in symbols:
            if symbol in text:
                return symbol.upper()

        return None

    def _determine_action_from_text(self, text: str) -> str:
        """Determine BUY/SELL from Form 4 text"""
        # Look for transaction type indicators in Form 4
        if 'open market purchase' in text or ('p' in text and 'purchase' in text):
            return 'BUY 📈'
        elif 'open market sale' in text or 'sale' in text and 'sell' in text:
            return 'SELL 📉'
        elif 'exercise of options' in text:
            return 'EXERCISE 📊'
        else:
            return 'TRADE 📊'

    def _fetch_google_news_trades(self) -> List[Dict]:
        """Fetch Congress trades from Google News (supplementary source)"""
        trades = []

        try:
            from xml.etree import ElementTree as ET

            query = 'Congress stock trading'
            rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

            print(f"[DEBUG] Fetching Google News: {query}")
            response = requests.get(rss_url, headers=self.headers, timeout=15)

            if response.status_code == 200:
                root = ET.fromstring(response.content)
                items = root.findall('.//item')
                print(f"[DEBUG] Found {len(items)} Google News items")

                for item in items[:20]:  # Process up to 20 items
                    try:
                        title_elem = item.find('title')
                        link_elem = item.find('link')
                        description_elem = item.find('description')

                        if title_elem is None or not title_elem.text:
                            continue

                        title = title_elem.text
                        link = link_elem.text if link_elem is not None else ''
                        description = description_elem.text if description_elem is not None else ''

                        # Create unique ID
                        trade_id = f"gnews_{title}_{datetime.now().date()}"

                        if trade_id not in self.seen_trades:
                            # Try to extract ticker and action from title/description
                            combined_text = f"{title} {description}".lower()
                            ticker = self._extract_ticker_from_text(combined_text)
                            action = self._determine_action_from_text(combined_text)

                            trades.append({
                                'politician_name': 'Congress Member',
                                'ticker': ticker if ticker else 'TBD',
                                'transaction_type': action if action else 'TRADE 📊',
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
                        print(f"[DEBUG] Error processing Google News item: {str(e)[:60]}")
                        continue

        except Exception as e:
            print(f"[DEBUG] Error fetching Google News: {str(e)[:80]}")

        return trades

    def format_trade_alert(self, trade: Dict) -> str:
        """Format alert"""
        politician = trade.get('politician_name', 'Unknown')
        ticker = trade.get('ticker', 'PENDING')
        action = trade.get('transaction_type', 'Filing')
        date = trade.get('transaction_date', 'Unknown')
        source = trade.get('source', 'Unknown')
        link = trade.get('link', '')
        summary = trade.get('summary', '')

        alert = f"📊 CONGRESSIONAL TRADE\n{politician}\n{action} {ticker}\nDate: {date}\nSource: {source}"
        if summary:
            alert += f"\n{summary[:60]}"
        if link:
            alert += f"\nView: {link[:70]}"
        alert += "\n---"

        return alert
