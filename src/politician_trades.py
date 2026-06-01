import requests
import json
from datetime import datetime, timedelta
from typing import List, Dict

class PoliticianTradeTracker:
    def __init__(self):
        self.senate_api = "https://senatestockwatcher.com/api/v1/trades"
        self.seen_trades_file = "data/seen_politician_trades.json"
        self.seen_trades = self._load_seen_trades()

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
        """Fetch recent politician trades from Senate Stock Watcher API"""
        try:
            response = requests.get(self.senate_api, timeout=10)
            response.raise_for_status()
            trades = response.json()

            new_trades = []
            for trade in trades:
                trade_id = trade.get('id', '')
                if trade_id not in self.seen_trades:
                    new_trades.append(trade)
                    self.seen_trades.add(trade_id)

            self._save_seen_trades()
            return new_trades
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

        return f"📈 POLITICIAN TRADE ALERT\n{politician} {action} {ticker}\nAmount: {amount}\nDate: {date}"
