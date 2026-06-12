import requests
import json
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
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
        """Fetch and analyze Congress trades from Google News"""
        trades = []

        print("[DEBUG] Fetching Congress trading news from Google News...")
        google_trades = self._fetch_and_analyze_google_news()
        print(f"[DEBUG] Found {len(google_trades)} trades with extracted ticker info")
        trades.extend(google_trades)

        self._save_seen_trades()
        return trades[:20]

    def _fetch_and_analyze_google_news(self) -> List[Dict]:
        """Fetch Google News and analyze articles for stock ticker and action"""
        trades = []

        queries = [
            'Congress stock trading',
            'Senate stock purchases',
            'Representative stock trading',
            'Congressional insider trades'
        ]

        for query in queries:
            try:
                rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
                print(f"[DEBUG] Fetching Google News for: {query}")

                response = requests.get(rss_url, headers=self.headers, timeout=15)

                if response.status_code == 200:
                    root = ET.fromstring(response.content)
                    items = root.findall('.//item')
                    print(f"[DEBUG] Found {len(items)} items for '{query}'")

                    for item in items[:20]:  # Analyze up to 20 articles per query
                        try:
                            title_elem = item.find('title')
                            link_elem = item.find('link')
                            pub_date_elem = item.find('pubDate')
                            description_elem = item.find('description')

                            title = title_elem.text if title_elem is not None else ''
                            link = link_elem.text if link_elem is not None else ''
                            pub_date = pub_date_elem.text if pub_date_elem is not None else str(datetime.now())
                            snippet = description_elem.text if description_elem is not None else ''

                            if not title or not link:
                                continue

                            # Try to scrape full article content
                            print(f"[DEBUG] Analyzing article: {title[:50]}")
                            article_data = self._scrape_and_analyze_article(link, title, snippet)

                            if article_data and article_data.get('ticker'):
                                trade_id = f"{article_data['ticker']}_{article_data['politician']}_{pub_date[:10]}"

                                if trade_id not in self.seen_trades:
                                    article_data['transaction_date'] = pub_date[:10]
                                    article_data['id'] = trade_id
                                    article_data['link'] = link
                                    trades.append(article_data)
                                    self.seen_trades.add(trade_id)
                                    print(f"[DEBUG] ✅ Added trade: {article_data['politician']} {article_data['transaction_type']} {article_data['ticker']}")

                        except Exception as e:
                            print(f"[DEBUG] Error processing item: {e}")
                            continue

            except Exception as e:
                print(f"[DEBUG] Error fetching {query}: {e}")

            time.sleep(1)

        return trades

    def _scrape_and_analyze_article(self, url: str, headline: str, snippet: str) -> Dict:
        """Scrape article content and extract ticker + buy/sell action"""
        try:
            # Try to get article content
            print(f"[DEBUG] Scraping article content from {url[:50]}...")
            response = requests.get(url, headers=self.headers, timeout=10)

            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                # Get all text from article
                paragraphs = soup.find_all(['p', 'div', 'article'])
                article_text = ' '.join([p.text for p in paragraphs[:10]])  # First 10 paragraphs
            else:
                # Use headline and snippet if we can't scrape
                article_text = f"{headline} {snippet}"

            combined_text = f"{headline} {snippet} {article_text}".lower()

            # Extract ticker from text
            ticker = self._extract_ticker(combined_text)
            if not ticker:
                print(f"[DEBUG] No ticker found in article")
                return None

            # Determine action (BUY, SELL, HOLD)
            action = self._determine_action(combined_text)

            # Extract politician name
            politician = self._extract_politician_name(headline)

            if not politician or politician == "Unknown":
                print(f"[DEBUG] Could not extract politician name")
                return None

            print(f"[DEBUG] Extracted: {politician} {action} {ticker}")

            return {
                'politician_name': politician,
                'ticker': ticker,
                'transaction_type': action,
                'amount': 'See Article',
                'summary': headline[:100]
            }

        except Exception as e:
            print(f"[DEBUG] Error analyzing article: {e}")
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

        print(f"[DEBUG] No ticker extracted from text")
        return None

    def _determine_action(self, text: str) -> str:
        """Determine if transaction is BUY, SELL, or HOLD"""
        buy_keywords = ['bought', 'purchased', 'acquired', 'invested', 'buying', 'buys', 'investment']
        sell_keywords = ['sold', 'selling', 'divested', 'liquidated', 'offloaded', 'dumped', 'sells']
        hold_keywords = ['holds', 'holding', 'maintains', 'maintaining', 'owned']

        buy_count = sum(1 for kw in buy_keywords if kw in text)
        sell_count = sum(1 for kw in sell_keywords if kw in text)
        hold_count = sum(1 for kw in hold_keywords if kw in text)

        if buy_count > sell_count and buy_count > 0:
            return "BUY 📈"
        elif sell_count > buy_count and sell_count > 0:
            return "SELL 📉"
        elif hold_count > 0:
            return "HOLD 💼"
        else:
            return "TRADE 📊"

    def _extract_politician_name(self, headline: str) -> str:
        """Extract politician name from headline"""
        # Look for "Rep./Sen./Representative/Senator Name"
        patterns = [
            r'(?:Rep|Representative|Sen|Senator|Congressman|Congresswoman)\s+(\w+\s+\w+)',
            r'(?:Rep|Sen)\.\s+(\w+\s+\w+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, headline, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                if len(name) > 2:
                    print(f"[DEBUG] Extracted politician: {name}")
                    return name

        # Try to extract a name from the beginning of headline
        words = headline.split()
        for i, word in enumerate(words):
            if any(title in word.lower() for title in ['rep', 'sen', 'representative', 'congressman', 'senator']):
                if i + 2 < len(words):
                    name = f"{words[i+1]} {words[i+2]}"
                    if name and name != "Unknown":
                        print(f"[DEBUG] Extracted politician from position: {name}")
                        return name

        return "Congress Member"

    def format_trade_alert(self, trade: Dict) -> str:
        """Format a trade into readable alert text"""
        politician = trade.get('politician_name', 'Unknown')
        ticker = trade.get('ticker', 'N/A')
        action = trade.get('transaction_type', 'TRADE')
        date = trade.get('transaction_date', 'Unknown')
        summary = trade.get('summary', '')
        link = trade.get('link', '')

        alert = f"📊 CONGRESS STOCK TRADE\n{politician}\n{action} {ticker}\nDate: {date}\nSource: Google News"
        if summary:
            alert += f"\nHeadline: {summary[:60]}"
        if link:
            alert += f"\nRead: {link[:80]}"
        alert += "\n---"

        return alert
