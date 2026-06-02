import requests
import json
from datetime import datetime, timedelta
from typing import List, Dict
from xml.etree import ElementTree as ET
from bs4 import BeautifulSoup
import time
import re

class PoliticianTradeTracker:
    def __init__(self):
        self.seen_trades_file = "data/seen_politician_trades.json"
        self.seen_trades = self._load_seen_trades()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/rss+xml,application/xml,text/html,*/*',
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
        """Fetch politician trades from multiple RSS feed sources"""
        trades = []

        # Try Google News RSS
        print("[DEBUG] Attempting Google News RSS...")
        trades.extend(self._fetch_google_news_trades())
        time.sleep(1)

        # Try financial news RSS feeds
        print("[DEBUG] Attempting financial news RSS feeds...")
        trades.extend(self._fetch_financial_rss_trades())
        time.sleep(1)

        # Try alternative SEC endpoints
        print("[DEBUG] Attempting alternative SEC data sources...")
        trades.extend(self._fetch_alternative_sec_trades())
        time.sleep(1)

        # Try CNBC and Bloomberg news
        print("[DEBUG] Attempting CNBC/Bloomberg feeds...")
        trades.extend(self._fetch_cnbc_bloomberg_trades())

        self._save_seen_trades()
        return trades[:20]

    def _fetch_google_news_trades(self) -> List[Dict]:
        """Fetch from Google News RSS for Congress trading news"""
        trades = []

        # Google News RSS feeds for Congress trading keywords
        queries = [
            'Congress stock trading',
            'Senate stock purchases',
            'Representative stock trading',
            'Congressional insider trades'
        ]

        for query in queries:
            try:
                # Google News RSS endpoint
                rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
                print(f"[DEBUG] Fetching Google News for: {query}")

                response = requests.get(rss_url, headers=self.headers, timeout=15)

                if response.status_code == 200:
                    print(f"[DEBUG] Got 200 from Google News")
                    try:
                        root = ET.fromstring(response.content)
                        items = root.findall('.//item')
                        print(f"[DEBUG] Found {len(items)} items")

                        for item in items[:15]:
                            try:
                                title_elem = item.find('title')
                                pub_date_elem = item.find('pubDate')
                                link_elem = item.find('link')

                                title = title_elem.text if title_elem is not None else ''
                                pub_date = pub_date_elem.text if pub_date_elem is not None else str(datetime.now())
                                link = link_elem.text if link_elem is not None else ''

                                if title and any(kw in title.upper() for kw in ['TRADE', 'BUY', 'SELL', 'STOCK']):
                                    trade_id = f"gnews_{title}_{pub_date[:10]}"

                                    if trade_id not in self.seen_trades and len(title) > 15:
                                        trades.append({
                                            'politician_name': title[:70],
                                            'ticker': 'Congress',
                                            'transaction_type': 'News Alert',
                                            'amount': 'See Article',
                                            'transaction_date': pub_date[:10],
                                            'id': trade_id,
                                            'source': 'Google News',
                                            'link': link
                                        })
                                        self.seen_trades.add(trade_id)
                                        print(f"[DEBUG] Added: {title[:40]}")

                            except Exception as e:
                                continue

                    except ET.ParseError as e:
                        print(f"[DEBUG] XML parse error: {e}")
                else:
                    print(f"[DEBUG] Got {response.status_code} from Google News")

            except Exception as e:
                print(f"[DEBUG] Error: {e}")

            time.sleep(0.5)

        return trades

    def _fetch_financial_rss_trades(self) -> List[Dict]:
        """Fetch from financial news RSS feeds"""
        trades = []

        rss_feeds = [
            {
                'name': 'CNBC Business',
                'url': 'https://www.cnbc.com/id/100003114/device/rss/rss.html'
            },
            {
                'name': 'Reuters Markets',
                'url': 'https://feeds.reuters.com/reuters/businessNews'
            },
            {
                'name': 'AP Business News',
                'url': 'https://apnews.com/apf-services/APIFeeds?formats=rss&tags=business'
            },
            {
                'name': 'Financial Times',
                'url': 'https://feeds.ft.com/markets'
            }
        ]

        for feed in rss_feeds:
            try:
                print(f"[DEBUG] Fetching {feed['name']}")
                response = requests.get(feed['url'], headers=self.headers, timeout=15)

                if response.status_code == 200:
                    print(f"[DEBUG] Got 200 from {feed['name']}")
                    try:
                        root = ET.fromstring(response.content)
                        items = root.findall('.//item')
                        print(f"[DEBUG] Found {len(items)} items from {feed['name']}")

                        for item in items[:20]:
                            try:
                                title_elem = item.find('title')
                                pub_date_elem = item.find('pubDate')
                                link_elem = item.find('link')

                                title = title_elem.text if title_elem is not None else ''
                                pub_date = pub_date_elem.text if pub_date_elem is not None else str(datetime.now())
                                link = link_elem.text if link_elem is not None else ''

                                if any(kw in title.upper() for kw in ['CONGRESS', 'SENATE', 'REPRESENTATIVE', 'TRADE', 'BUY STOCK']):
                                    trade_id = f"{feed['name']}_{title}_{pub_date[:10]}"

                                    if trade_id not in self.seen_trades and len(title) > 15:
                                        trades.append({
                                            'politician_name': title[:70],
                                            'ticker': 'Congress',
                                            'transaction_type': 'Business News',
                                            'amount': 'See Article',
                                            'transaction_date': pub_date[:10],
                                            'id': trade_id,
                                            'source': feed['name'],
                                            'link': link
                                        })
                                        self.seen_trades.add(trade_id)
                                        print(f"[DEBUG] Added from {feed['name']}: {title[:40]}")

                            except:
                                continue

                    except ET.ParseError as e:
                        print(f"[DEBUG] XML parse error from {feed['name']}: {e}")
                else:
                    print(f"[DEBUG] Got {response.status_code} from {feed['name']}")

            except Exception as e:
                print(f"[DEBUG] Error fetching {feed['name']}: {e}")

            time.sleep(0.5)

        return trades

    def _fetch_alternative_sec_trades(self) -> List[Dict]:
        """Try alternative SEC endpoints that might not be blocked"""
        trades = []

        alt_urls = [
            'https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=4&dateb=&owner=exclude&count=40&CIK=',
            'https://www.sec.gov/edgar/browse/?CIK=',
        ]

        for url in alt_urls:
            try:
                print(f"[DEBUG] Trying alternative SEC endpoint")
                response = requests.get(url, headers=self.headers, timeout=10)

                if response.status_code == 200:
                    print(f"[DEBUG] Alternative SEC endpoint worked!")
                    # If we get here, parse the response
                    soup = BeautifulSoup(response.content, 'html.parser')
                    tables = soup.find_all('table')
                    print(f"[DEBUG] Found {len(tables)} tables")

                    if tables:
                        for table in tables[:2]:
                            rows = table.find_all('tr')[1:20]
                            for row in rows:
                                try:
                                    cols = row.find_all('td')
                                    if len(cols) >= 2:
                                        company = cols[0].text.strip()[:50]
                                        date = cols[-1].text.strip()

                                        trade_id = f"alt_sec_{company}_{date}"
                                        if trade_id not in self.seen_trades and company:
                                            trades.append({
                                                'politician_name': company,
                                                'ticker': 'SEC',
                                                'transaction_type': 'Form 4',
                                                'amount': 'See SEC',
                                                'transaction_date': date,
                                                'id': trade_id,
                                                'source': 'SEC Alternative'
                                            })
                                            self.seen_trades.add(trade_id)
                                            print(f"[DEBUG] Added: {company}")
                                except:
                                    continue
                else:
                    print(f"[DEBUG] Alt SEC got {response.status_code}")

            except Exception as e:
                print(f"[DEBUG] Alt SEC error: {e}")

            time.sleep(0.5)

        return trades

    def _fetch_cnbc_bloomberg_trades(self) -> List[Dict]:
        """Fetch from CNBC and Bloomberg direct URLs"""
        trades = []

        sources = [
            {
                'name': 'CNBC Congress Trades',
                'url': 'https://www.cnbc.com/search/?query=congress%20stock%20trading'
            },
            {
                'name': 'Bloomberg Politics',
                'url': 'https://www.bloomberg.com/politics'
            }
        ]

        for source in sources:
            try:
                print(f"[DEBUG] Fetching {source['name']}")
                response = requests.get(source['url'], headers=self.headers, timeout=15)

                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    links = soup.find_all('a', href=True)
                    print(f"[DEBUG] Found {len(links)} links from {source['name']}")

                    for link in links[:30]:
                        title = link.text.strip()

                        if any(kw in title.upper() for kw in ['TRADE', 'CONGRESS', 'SENATE', 'STOCK']):
                            trade_id = f"{source['name']}_{title}_{datetime.now().date()}"

                            if trade_id not in self.seen_trades and len(title) > 10:
                                trades.append({
                                    'politician_name': title[:70],
                                    'ticker': 'Congress',
                                    'transaction_type': 'Media Report',
                                    'amount': 'See Article',
                                    'transaction_date': str(datetime.now().date()),
                                    'id': trade_id,
                                    'source': source['name']
                                })
                                self.seen_trades.add(trade_id)
                                print(f"[DEBUG] Added from {source['name']}: {title[:40]}")

                else:
                    print(f"[DEBUG] Got {response.status_code} from {source['name']}")

            except Exception as e:
                print(f"[DEBUG] Error from {source['name']}: {e}")

            time.sleep(0.5)

        return trades

    def format_trade_alert(self, trade: Dict) -> str:
        """Format a trade into readable alert text"""
        politician = trade.get('politician_name', 'Unknown')
        filing_type = trade.get('transaction_type', 'Unknown')
        date = trade.get('transaction_date', 'Unknown')
        source = trade.get('source', 'Financial News')

        alert = f"📈 CONGRESS TRADING ALERT\nHeadline: {politician}\nType: {filing_type}\nDate: {date}\nSource: {source}"
        if trade.get('link'):
            alert += f"\nRead: {trade['link']}"
        alert += "\n---"

        return alert
