import requests
import json
from datetime import datetime, timedelta
from typing import List, Dict
import time
import re

class PoliticianTradeTracker:
    def __init__(self):
        self.seen_trades_file = "data/seen_politician_trades.json"
        self.seen_trades = self._load_seen_trades()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
        # Congressional/political figure company names to watch
        self.political_keywords = [
            'trump', 'biden', 'harris', 'pence', 'pelosi', 'mccarthy', 'schumer', 'mcconnell',
            'marjorie taylor greene', 'aoc', 'alexandria ocasio-cortez', 'matt gaetz', 'jim jordan',
            'ilhan omar', 'rashida tlaib', 'sen.', 'rep.', 'representative', 'senator', 'congress',
            'congressional', 'house of representatives', 'trust for', 'foundation'
        ]
        # Common stock symbols and company name mappings
        self.ticker_map = {
            'apple': 'AAPL', 'microsoft': 'MSFT', 'google': 'GOOGL', 'amazon': 'AMZN',
            'tesla': 'TSLA', 'nvidia': 'NVDA', 'meta': 'META', 'facebook': 'META',
            'nvidia corporation': 'NVDA', 'tesla inc': 'TSLA', 'netflix': 'NFLX',
            'intel': 'INTC', 'amd': 'AMD', 'qualcomm': 'QCOM', 'broadcom': 'AVGO',
            'berkshire': 'BRK.B', 'jpmorgan': 'JPM', 'goldman sachs': 'GS',
            'morgan stanley': 'MS', 'citigroup': 'C', 'bank of america': 'BAC',
            'wells fargo': 'WFC', 'pfizer': 'PFE', 'moderna': 'MRNA',
            'johnson & johnson': 'JNJ', 'coca cola': 'KO', 'pepsi': 'PEP',
            'walmart': 'WMT', 'target': 'TGT', 'costco': 'COST', 'home depot': 'HD'
        }

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
        """Fetch Congress trades from SEC bulk data"""
        trades = []

        print("[DEBUG] Fetching Congress trades from SEC bulk data files...")
        sec_trades = self._fetch_sec_form4_trades()
        print(f"[DEBUG] Found {len(sec_trades)} congressional trades from SEC")
        trades.extend(sec_trades)

        self._save_seen_trades()
        return trades[:20]

    def _fetch_sec_form4_trades(self) -> List[Dict]:
        """Fetch Form 4 filings from SEC bulk data"""
        trades = []

        try:
            # Get today's and yesterday's dates for filing index
            today = datetime.now()
            yesterday = today - timedelta(days=1)

            dates_to_check = [today, yesterday]

            for date in dates_to_check:
                date_str = date.strftime('%Y%m%d')
                print(f"[DEBUG] Checking SEC filings for {date_str}")

                # SEC provides daily index files
                # Format: https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=4&dateb=YYYYMMDD&owner=exclude&count=100
                url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=4&dateb={date_str}&owner=exclude&count=100"

                try:
                    response = requests.get(url, headers=self.headers, timeout=15)

                    if response.status_code == 200:
                        print(f"[DEBUG] Got Form 4 filings from SEC for {date_str}")

                        # Parse HTML table to extract filings
                        trades_found = self._parse_sec_form4_table(response.text, date_str)
                        trades.extend(trades_found)
                        print(f"[DEBUG] Found {len(trades_found)} Form 4 filings")
                    else:
                        print(f"[DEBUG] Got {response.status_code} from SEC for {date_str}")

                except Exception as e:
                    print(f"[DEBUG] Error fetching Form 4 for {date_str}: {e}")
                    continue

                time.sleep(1)  # Be respectful to SEC

        except Exception as e:
            print(f"[DEBUG] Error in _fetch_sec_form4_trades: {e}")

        return trades

    def _parse_sec_form4_table(self, html: str, date_str: str) -> List[Dict]:
        """Parse SEC HTML table for Form 4 filings"""
        trades = []

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')

            # Find the results table
            table = soup.find('table', {'class': 'tableFile'})
            if not table:
                print(f"[DEBUG] No table found in SEC response")
                return trades

            rows = table.find_all('tr')[1:]  # Skip header
            print(f"[DEBUG] Found {len(rows)} Form 4 rows")

            for row in rows[:50]:  # Check first 50 filings
                try:
                    cols = row.find_all('td')
                    if len(cols) < 4:
                        continue

                    company_name = cols[0].text.strip()
                    cik = cols[1].text.strip()
                    filing_date = cols[3].text.strip()

                    # Check if this is a political figure or Congressional trust
                    is_political = any(kw in company_name.lower() for kw in self.political_keywords)

                    if is_political:
                        print(f"[DEBUG] Found political filing: {company_name}")

                        trade_id = f"sec_{cik}_{filing_date}_{company_name}"

                        if trade_id not in self.seen_trades:
                            # Try to get more details about the filing
                            filing_link = cols[1].find('a')
                            if filing_link:
                                filing_url = f"https://www.sec.gov{filing_link.get('href', '')}"
                                details = self._fetch_form4_details(filing_url)

                                if details:
                                    details['id'] = trade_id
                                    trades.append(details)
                                    self.seen_trades.add(trade_id)
                                    print(f"[DEBUG] ✅ Added SEC Form 4: {company_name}")

                except Exception as e:
                    print(f"[DEBUG] Error parsing row: {e}")
                    continue

        except Exception as e:
            print(f"[DEBUG] Error parsing SEC table: {e}")

        return trades

    def _fetch_form4_details(self, filing_url: str) -> Dict:
        """Fetch Form 4 filing details to extract trade information"""
        try:
            print(f"[DEBUG] Fetching Form 4 details from {filing_url[:60]}")
            response = requests.get(filing_url, headers=self.headers, timeout=10)

            if response.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.content, 'html.parser')

                # Get text content
                text = soup.get_text().lower()

                # Extract ticker and action
                ticker = self._extract_ticker(text)
                action = self._determine_action(text)

                # Extract filer name
                filer_match = re.search(r'reporting owner:\s*([^<\n]+)', text)
                filer_name = filer_match.group(1).strip() if filer_match else 'Congressional Official'

                if ticker and action:
                    return {
                        'politician_name': filer_name[:50],
                        'ticker': ticker,
                        'transaction_type': action,
                        'amount': 'See SEC Filing',
                        'summary': f'Form 4 Filing - {filer_name}',
                        'transaction_date': datetime.now().strftime('%Y-%m-%d'),
                        'source': 'SEC Form 4',
                        'link': filing_url
                    }

        except Exception as e:
            print(f"[DEBUG] Error fetching Form 4 details: {e}")

        return None

    def _extract_ticker(self, text: str) -> str:
        """Extract stock ticker from text"""
        # Look for $TICKER pattern
        ticker_pattern = r'\$([A-Z]{1,5})\b'
        match = re.search(ticker_pattern, text)
        if match:
            ticker = match.group(1)
            print(f"[DEBUG] Found ticker via $ pattern: {ticker}")
            return ticker

        # Look for common company names and map to tickers
        for company_name, ticker in self.ticker_map.items():
            if company_name in text:
                print(f"[DEBUG] Found company name '{company_name}' -> ticker: {ticker}")
                return ticker

        # Try to find common ticker patterns (usually ALL CAPS)
        uppercase_words = re.findall(r'\b([A-Z]{1,5})\b', text)
        for word in uppercase_words:
            if word in self.ticker_map.values():
                print(f"[DEBUG] Found ticker via pattern: {word}")
                return word

        return None

    def _determine_action(self, text: str) -> str:
        """Determine if transaction is BUY, SELL, or HOLD"""
        buy_keywords = ['buy', 'purchase', 'acquired', 'invest', 'open acquisition']
        sell_keywords = ['sell', 'dispose', 'divest', 'liquidat', 'closing']

        buy_count = sum(1 for kw in buy_keywords if kw in text)
        sell_count = sum(1 for kw in sell_keywords if kw in text)

        if buy_count > sell_count and buy_count > 0:
            return "BUY 📈"
        elif sell_count > buy_count and sell_count > 0:
            return "SELL 📉"
        elif buy_count > 0 or sell_count > 0:
            return "TRADE 📊"
        else:
            return None

    def format_trade_alert(self, trade: Dict) -> str:
        """Format a trade into readable alert text"""
        politician = trade.get('politician_name', 'Unknown')
        ticker = trade.get('ticker', 'N/A')
        action = trade.get('transaction_type', 'TRADE')
        date = trade.get('transaction_date', 'Unknown')
        summary = trade.get('summary', '')
        link = trade.get('link', '')
        source = trade.get('source', 'SEC')

        alert = f"📊 CONGRESSIONAL TRADE (SEC Form 4)\n{politician}\n{action} {ticker}\nDate: {date}"
        if summary:
            alert += f"\nFiling: {summary}"
        if link:
            alert += f"\nView: {link[:80]}"
        alert += "\n---"

        return alert
