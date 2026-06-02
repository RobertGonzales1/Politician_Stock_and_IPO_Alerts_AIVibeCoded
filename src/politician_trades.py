import requests
import json
from datetime import datetime, timedelta
from typing import List, Dict
from xml.etree import ElementTree as ET
from bs4 import BeautifulSoup
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
        """Fetch politician trades from multiple sources with debugging"""
        trades = []

        # Try SEC RSS first
        print("[DEBUG] Attempting SEC RSS feeds for Form 4 filings...")
        sec_trades = self._fetch_sec_rss_trades()
        print(f"[DEBUG] SEC RSS returned {len(sec_trades)} trades")
        trades.extend(sec_trades)
        time.sleep(1)

        # Try news sources for Congress trading news
        print("[DEBUG] Attempting financial news sources for Congress trades...")
        news_trades = self._fetch_news_congress_trades()
        print(f"[DEBUG] News sources returned {len(news_trades)} trades")
        trades.extend(news_trades)
        time.sleep(1)

        # Try House.gov directly
        print("[DEBUG] Attempting House.gov financial disclosures...")
        house_trades = self._fetch_house_gov_trades()
        print(f"[DEBUG] House.gov returned {len(house_trades)} trades")
        trades.extend(house_trades)

        self._save_seen_trades()
        return trades[:20]

    def _fetch_sec_rss_trades(self) -> List[Dict]:
        """Fetch from SEC RSS feeds"""
        trades = []
        rss_urls = [
            "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=4&dateb=&owner=exclude&match=&count=100&format=atom",
            "https://www.sec.gov/feeds/form-4",
        ]

        for rss_url in rss_urls:
            try:
                print(f"[DEBUG] Fetching {rss_url}")
                response = requests.get(rss_url, headers=self.headers, timeout=15)

                if response.status_code == 200:
                    print(f"[DEBUG] Got 200 response from {rss_url}")
                    try:
                        root = ET.fromstring(response.content)
                        namespaces = {
                            'atom': 'http://www.w3.org/2005/Atom',
                            'content': 'http://purl.org/rss/1.0/modules/content/'
                        }

                        entries = root.findall('atom:entry', namespaces)
                        if not entries:
                            entries = root.findall('.//item')

                        print(f"[DEBUG] Found {len(entries)} entries in RSS")

                        for entry in entries[:40]:
                            try:
                                title_elem = entry.find('atom:title', namespaces)
                                published_elem = entry.find('atom:published', namespaces)
                                summary_elem = entry.find('atom:summary', namespaces)

                                if title_elem is None:
                                    title_elem = entry.find('title')
                                if published_elem is None:
                                    published_elem = entry.find('pubDate')
                                if summary_elem is None:
                                    summary_elem = entry.find('description')

                                title = title_elem.text if title_elem is not None else ''
                                published = published_elem.text if published_elem is not None else str(datetime.now())
                                summary = summary_elem.text if summary_elem is not None else ''

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
                                        print(f"[DEBUG] Added trade: {company_name}")

                            except Exception as e:
                                continue

                        if trades:
                            print(f"[DEBUG] RSS feed successful, found {len(trades)} new trades")
                            break

                    except ET.ParseError as e:
                        print(f"[DEBUG] XML Parse error: {e}")
                        continue
                else:
                    print(f"[DEBUG] Got {response.status_code} from {rss_url}")

            except requests.RequestException as e:
                print(f"[DEBUG] Request error from {rss_url}: {e}")
                continue

        return trades

    def _fetch_news_congress_trades(self) -> List[Dict]:
        """Fetch Congress trading news from financial sites"""
        trades = []

        news_sources = [
            {
                'name': 'Yahoo Finance Congress',
                'url': 'https://finance.yahoo.com/news/congress-stock-trades/'
            },
            {
                'name': 'MarketWatch Congress',
                'url': 'https://www.marketwatch.com/news/congress-stock-trades'
            }
        ]

        for source in news_sources:
            try:
                print(f"[DEBUG] Fetching {source['name']} from {source['url']}")
                response = requests.get(source['url'], headers=self.headers, timeout=15)

                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    articles = soup.find_all(['a', 'h2', 'h3'])[:30]

                    print(f"[DEBUG] Found {len(articles)} articles from {source['name']}")

                    for article in articles:
                        try:
                            title = article.text.strip()

                            if any(keyword in title.upper() for keyword in ['CONGRESS', 'SENATE', 'HOUSE', 'TRADE', 'BUY', 'SELL']):
                                trade_id = f"{source['name']}_{title}_{datetime.now().date()}"

                                if trade_id not in self.seen_trades and len(title) > 10:
                                    trades.append({
                                        'politician_name': title[:60],
                                        'ticker': 'Congress',
                                        'transaction_type': 'News Report',
                                        'amount': 'See Article',
                                        'transaction_date': str(datetime.now().date()),
                                        'id': trade_id,
                                        'source': source['name']
                                    })
                                    self.seen_trades.add(trade_id)
                                    print(f"[DEBUG] Added news trade: {title[:40]}")

                        except:
                            continue

                else:
                    print(f"[DEBUG] Got {response.status_code} from {source['name']}")

            except Exception as e:
                print(f"[DEBUG] Error from {source['name']}: {e}")
                continue

            time.sleep(1)

        return trades

    def _fetch_house_gov_trades(self) -> List[Dict]:
        """Fetch from House.gov financial disclosures"""
        trades = []

        try:
            url = "https://disclosures-clerk.house.gov/public_disc/"
            print(f"[DEBUG] Fetching House.gov disclosures from {url}")

            response = requests.get(url, headers=self.headers, timeout=15)

            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                links = soup.find_all('a', href=True)[:50]

                print(f"[DEBUG] Found {len(links)} links on House.gov")

                for link in links:
                    href = link.get('href', '')
                    text = link.text.strip()

                    if any(keyword in text.lower() for keyword in ['transaction', 'trade', 'stock', 'filing']):
                        trade_id = f"house_{text}_{datetime.now().date()}"

                        if trade_id not in self.seen_trades and len(text) > 5:
                            trades.append({
                                'politician_name': text[:50],
                                'ticker': 'Congress',
                                'transaction_type': 'House Disclosure',
                                'amount': 'See Link',
                                'transaction_date': str(datetime.now().date()),
                                'id': trade_id,
                                'link': url + href if not href.startswith('http') else href
                            })
                            self.seen_trades.add(trade_id)
                            print(f"[DEBUG] Added House trade: {text[:40]}")

            else:
                print(f"[DEBUG] Got {response.status_code} from House.gov")

        except Exception as e:
            print(f"[DEBUG] Error fetching House.gov: {e}")

        return trades

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
