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
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
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
        """Scrape recent politician trades from House.gov SOPR filings"""
        trades = []
        try:
            # Scrape House SOPR (Senate Personal Office Reporting)
            url = "https://disclosures-clerk.house.gov/public_disc/SOPR-2024.html"
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Look for tables with transaction data
            tables = soup.find_all('table')

            for table in tables:
                rows = table.find_all('tr')[1:50]  # Limit to first 50 rows

                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 5:
                        try:
                            politician = cols[0].text.strip()
                            ticker = cols[1].text.strip()
                            transaction_type = cols[2].text.strip()
                            amount = cols[3].text.strip()
                            date = cols[4].text.strip()

                            trade_id = f"{politician}_{ticker}_{date}_{transaction_type}"

                            if trade_id not in self.seen_trades and politician and ticker:
                                trades.append({
                                    'politician_name': politician,
                                    'ticker': ticker,
                                    'transaction_type': transaction_type,
                                    'amount': amount,
                                    'transaction_date': date,
                                    'id': trade_id
                                })
                                self.seen_trades.add(trade_id)
                        except (IndexError, AttributeError):
                            continue

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
        amount = trade.get('amount', 'Unknown')
        date = trade.get('transaction_date', 'Unknown')

        return f"📈 POLITICIAN TRADE ALERT\n{politician} {action} {ticker}\nAmount: {amount}\nDate: {date}\n---"
