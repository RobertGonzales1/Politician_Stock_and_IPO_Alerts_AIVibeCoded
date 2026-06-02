import requests
import json
from datetime import datetime, timedelta
from typing import List, Dict
from bs4 import BeautifulSoup
import re

class PoliticianTradeTracker:
    def __init__(self):
        self.seen_trades_file = "data/seen_politician_trades.json"
        self.seen_trades = self._load_seen_trades()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://www.house.gov'
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
        """Scrape recent politician trades from House disclosures"""
        trades = []
        try:
            # Try House clerk disclosures - recent filings
            url = "https://disclosures-clerk.house.gov/public_disc/"
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Look for links to recent filings
            links = soup.find_all('a', href=re.compile(r'\.htm|\.html'))

            recent_trades = []
            for link in links[:30]:  # Check first 30 links
                href = link.get('href', '')
                text = link.text.strip()

                # Look for transaction-related files
                if any(keyword in text.lower() for keyword in ['transaction', 'trade', 'stock', '2026', '2025']):
                    try:
                        file_url = url + href if not href.startswith('http') else href
                        file_response = requests.get(file_url, headers=self.headers, timeout=10)

                        if file_response.status_code == 200:
                            file_soup = BeautifulSoup(file_response.content, 'html.parser')
                            # Extract any trade information found
                            text_content = file_soup.get_text()

                            # Simple pattern matching for trades
                            if any(ticker in text_content.upper() for ticker in ['AAPL', 'MSFT', 'NVDA', 'TSLA', 'META']):
                                trade_id = f"{href}_{datetime.now().date()}"
                                if trade_id not in self.seen_trades:
                                    recent_trades.append({
                                        'politician_name': text[:50],
                                        'ticker': 'Multiple',
                                        'transaction_type': 'Various',
                                        'amount': 'See SEC Link',
                                        'transaction_date': str(datetime.now().date()),
                                        'id': trade_id,
                                        'source_url': file_url
                                    })
                                    self.seen_trades.add(trade_id)
                    except:
                        continue

            trades = recent_trades[:10]  # Limit results
            self._save_seen_trades()
            return trades

        except requests.RequestException as e:
            print(f"Error fetching politician trades: {e}")
            return []

    def format_trade_alert(self, trade: Dict) -> str:
        """Format a trade into readable alert text"""
        politician = trade.get('politician_name', 'Unknown')
        ticker = trade.get('ticker', 'Unknown')
        action = trade.get('transaction_type', 'Unknown').upper()
        date = trade.get('transaction_date', 'Unknown')
        source_url = trade.get('source_url', '')

        alert = f"📈 POLITICIAN TRADE ALERT\nFiling: {politician}\nTicker(s): {ticker}\nDate: {date}"
        if source_url:
            alert += f"\nSource: {source_url}"
        alert += "\n---"
        return alert
