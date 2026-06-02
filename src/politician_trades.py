import requests
import json
from datetime import datetime, timedelta
from typing import List, Dict
from xml.etree import ElementTree as ET
import time

class PoliticianTradeTracker:
    def __init__(self):
        self.seen_trades_file = "data/seen_politician_trades.json"
        self.seen_trades = self._load_seen_trades()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/rss+xml,application/xml,text/html,*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.sec.gov/'
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
        """Fetch politician trades from SEC Form 4 filings via RSS feeds"""
        trades = []

        try:
            # Use SEC RSS feed for Form 4 filings (insider/political trades)
            rss_urls = [
                "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=4&dateb=&owner=exclude&match=&count=100&format=atom",
                "https://www.sec.gov/feeds/form-4",
            ]

            session = requests.Session()

            for rss_url in rss_urls:
                try:
                    response = session.get(rss_url, headers=self.headers, timeout=15)

                    if response.status_code == 200:
                        # Parse Atom/RSS feed
                        try:
                            root = ET.fromstring(response.content)

                            namespaces = {
                                'atom': 'http://www.w3.org/2005/Atom',
                                'content': 'http://purl.org/rss/1.0/modules/content/'
                            }

                            # Try Atom format
                            entries = root.findall('atom:entry', namespaces)
                            if not entries:
                                entries = root.findall('.//item')

                            for entry in entries[:40]:
                                try:
                                    # Atom format
                                    title_elem = entry.find('atom:title', namespaces)
                                    published_elem = entry.find('atom:published', namespaces)
                                    summary_elem = entry.find('atom:summary', namespaces)

                                    # RSS format fallback
                                    if title_elem is None:
                                        title_elem = entry.find('title')
                                    if published_elem is None:
                                        published_elem = entry.find('pubDate')
                                    if summary_elem is None:
                                        summary_elem = entry.find('description')

                                    title = title_elem.text if title_elem is not None else ''
                                    published = published_elem.text if published_elem is not None else str(datetime.now())
                                    summary = summary_elem.text if summary_elem is not None else ''

                                    # Extract filing info from title
                                    if 'Form 4' in title or '4' in title:
                                        parts = title.split('-')
                                        company_name = parts[0].strip() if parts else title[:50]
                                        cik = parts[1].strip()[:10] if len(parts) > 1 else ''

                                        trade_id = f"{cik}_{company_name}_{published[:10]}"

                                        if trade_id not in self.seen_trades:
                                            trades.append({
                                                'politician_name': company_name,
                                                'ticker': cik,
                                                'transaction_type': 'Form 4 Filing',
                                                'amount': 'See SEC Filing',
                                                'transaction_date': published[:10],
                                                'id': trade_id,
                                                'summary': summary[:100] if summary else ''
                                            })
                                            self.seen_trades.add(trade_id)

                                except Exception as e:
                                    continue

                            if trades:
                                break

                        except ET.ParseError as e:
                            print(f"Error parsing XML: {e}")
                            continue

                    time.sleep(1)

                except requests.RequestException as e:
                    print(f"Error fetching from {rss_url}: {e}")
                    continue

            self._save_seen_trades()
            return trades[:20]

        except Exception as e:
            print(f"Error fetching politician trades: {e}")
            return []

    def format_trade_alert(self, trade: Dict) -> str:
        """Format a trade into readable alert text"""
        politician = trade.get('politician_name', 'Unknown')
        filing_type = trade.get('transaction_type', 'Unknown')
        date = trade.get('transaction_date', 'Unknown')
        summary = trade.get('summary', '')

        alert = f"📈 POLITICAL INSIDER TRADE\nFiler: {politician}\nType: {filing_type}\nDate: {date}"
        if summary:
            alert += f"\nDetails: {summary}"
        alert += "\nView on SEC: https://www.sec.gov/cgi-bin/browse-edgar?type=4"
        alert += "\n---"

        return alert
