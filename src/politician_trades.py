import requests
import json
from datetime import datetime, timedelta
from typing import List, Dict
from bs4 import BeautifulSoup
import time

class PoliticianTradeTracker:
    def __init__(self):
        self.seen_trades_file = "data/seen_politician_trades.json"
        self.seen_trades = self._load_seen_trades()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        # Known CIKs for major Congressional members (partial list for demo)
        self.congressional_ciks = self._get_congressional_ciks()

    def _get_congressional_ciks(self) -> List[str]:
        """Get CIKs of known Congressional members from recent filings"""
        return []  # Will be populated from SEC EDGAR searches

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
        """Fetch politician trades from SEC filings and public disclosures"""
        trades = []

        try:
            # Method 1: Check SEC EDGAR for Form 4 filings (insider trades)
            # Form 4s are required for officials with stock holdings
            url = "https://www.sec.gov/cgi-json/browse-edgar?action=getcompany&type=4&count=100"

            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()

            data = response.json()
            filings = data.get('filings', {}).get('filing', [])

            # Process recent Form 4 filings
            for filing in filings[:50]:
                try:
                    company_name = filing.get('company_name', '')
                    cik = filing.get('cik_str', '')
                    date = filing.get('filing_date', '')

                    # Filter for known political figures/companies
                    political_keywords = ['trust', 'senate', 'congress', 'house', 'representative', 'senator']
                    is_political = any(keyword in company_name.lower() for keyword in political_keywords)

                    if is_political or cik:
                        trade_id = f"{cik}_{date}_{company_name}"

                        if trade_id not in self.seen_trades:
                            trades.append({
                                'politician_name': company_name[:60],
                                'ticker': cik,
                                'transaction_type': 'Form 4 Filing',
                                'amount': 'See SEC Filing',
                                'transaction_date': date,
                                'id': trade_id,
                                'sec_link': f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=4&owner=exclude"
                            })
                            self.seen_trades.add(trade_id)
                except Exception as e:
                    continue

            # Add delay to be respectful to SEC servers
            time.sleep(1)

            self._save_seen_trades()
            return trades[:20]  # Limit to 20 results

        except requests.RequestException as e:
            print(f"Error fetching politician trades: {e}")
            return []

    def format_trade_alert(self, trade: Dict) -> str:
        """Format a trade into readable alert text"""
        politician = trade.get('politician_name', 'Unknown')
        filing_type = trade.get('transaction_type', 'Unknown')
        date = trade.get('transaction_date', 'Unknown')
        sec_link = trade.get('sec_link', '')

        alert = f"📈 CONGRESSIONAL TRADE ALERT\nFiler: {politician}\nType: {filing_type}\nDate: {date}"
        if sec_link:
            alert += f"\nView: {sec_link}"
        alert += "\n---"

        return alert
