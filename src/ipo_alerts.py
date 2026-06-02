import requests
import json
from datetime import datetime, timedelta
from typing import List, Dict
from bs4 import BeautifulSoup
import time
import re

class IPOTracker:
    def __init__(self):
        self.seen_ipos_file = "data/seen_ipos.json"
        self.seen_ipos = self._load_seen_ipos()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.google.com'
        }

    def _load_seen_ipos(self) -> set:
        try:
            with open(self.seen_ipos_file, 'r') as f:
                return set(json.load(f))
        except FileNotFoundError:
            return set()

    def _save_seen_ipos(self):
        import os
        os.makedirs('data', exist_ok=True)
        with open(self.seen_ipos_file, 'w') as f:
            json.dump(list(self.seen_ipos), f)

    def get_upcoming_ipos(self) -> List[Dict]:
        """Fetch IPOs from financial news sources (more reliable than SEC scraping)"""
        ipos = []

        # Method 1: Scrape MarketWatch IPO calendar
        ipos.extend(self._scrape_marketwatch_ipos())
        time.sleep(2)

        # Method 2: Scrape financial news for IPO announcements
        ipos.extend(self._scrape_financial_news_ipos())
        time.sleep(2)

        # Method 3: Try SEC RSS as backup
        ipos.extend(self._scrape_sec_rss_ipos())

        self._save_seen_ipos()
        return ipos[:30]

    def _scrape_marketwatch_ipos(self) -> List[Dict]:
        """Scrape MarketWatch IPO calendar"""
        ipos = []
        try:
            url = "https://www.marketwatch.com/tools/ipo-calendar"
            response = requests.get(url, headers=self.headers, timeout=15)

            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')

                # Look for IPO table rows
                rows = soup.find_all('tr')

                for row in rows:
                    try:
                        cols = row.find_all('td')
                        if len(cols) >= 3:
                            company_elem = cols[0].find('a')
                            if company_elem:
                                company_name = company_elem.text.strip()
                                expected_date = cols[1].text.strip() if len(cols) > 1 else ''
                                price_range = cols[2].text.strip() if len(cols) > 2 else ''

                                if company_name and expected_date:
                                    ipo_id = f"mw_{company_name}_{expected_date}"

                                    if ipo_id not in self.seen_ipos:
                                        ipos.append({
                                            'company': company_name,
                                            'cik': '',
                                            'filing_date': expected_date,
                                            'type': 'Expected IPO',
                                            'price_range': price_range,
                                            'source': 'MarketWatch',
                                            'sec_url': f"https://www.marketwatch.com/tools/ipo-calendar"
                                        })
                                        self.seen_ipos.add(ipo_id)
                    except:
                        continue

        except Exception as e:
            print(f"Error scraping MarketWatch: {e}")

        return ipos

    def _scrape_financial_news_ipos(self) -> List[Dict]:
        """Scrape financial news for recent IPO announcements"""
        ipos = []

        news_sources = [
            {
                'name': 'Yahoo Finance IPO',
                'url': 'https://finance.yahoo.com/news/ipos/',
                'parser': self._parse_yahoo_ipos
            }
        ]

        for source in news_sources:
            try:
                response = requests.get(source['url'], headers=self.headers, timeout=15)

                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    ipos.extend(source['parser'](soup))

            except Exception as e:
                print(f"Error scraping {source['name']}: {e}")

            time.sleep(1)

        return ipos

    def _parse_yahoo_ipos(self, soup: BeautifulSoup) -> List[Dict]:
        """Parse Yahoo Finance IPO news"""
        ipos = []
        try:
            articles = soup.find_all('a', {'data-test-id': 'quoteLink'})[:30]

            for article in articles:
                try:
                    title = article.text.strip()

                    if 'IPO' in title.upper() or 'Goes Public' in title:
                        company_match = re.search(r'([A-Z][A-Za-z\s]+?)(?:\s+(?:IPO|Goes Public))', title)
                        if company_match:
                            company_name = company_match.group(1).strip()

                            ipo_id = f"yf_{company_name}_{datetime.now().date()}"

                            if ipo_id not in self.seen_ipos and len(company_name) > 2:
                                ipos.append({
                                    'company': company_name,
                                    'cik': '',
                                    'filing_date': str(datetime.now().date()),
                                    'type': 'Recent IPO News',
                                    'source': 'Yahoo Finance',
                                    'sec_url': 'https://finance.yahoo.com/news/ipos/'
                                })
                                self.seen_ipos.add(ipo_id)
                except:
                    continue

        except Exception as e:
            print(f"Error parsing Yahoo Finance: {e}")

        return ipos

    def _scrape_sec_rss_ipos(self) -> List[Dict]:
        """Scrape SEC RSS as backup"""
        ipos = []
        try:
            from xml.etree import ElementTree as ET

            url = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=S-1&dateb=&owner=exclude&match=&count=100&format=atom"
            response = requests.get(url, headers=self.headers, timeout=15)

            if response.status_code == 200:
                try:
                    root = ET.fromstring(response.content)
                    namespaces = {'atom': 'http://www.w3.org/2005/Atom'}
                    entries = root.findall('atom:entry', namespaces)[:20]

                    for entry in entries:
                        try:
                            title_elem = entry.find('atom:title', namespaces)
                            published_elem = entry.find('atom:published', namespaces)

                            if title_elem is not None and published_elem is not None:
                                title = title_elem.text
                                published = published_elem.text[:10]

                                if 'S-1' in title:
                                    company = title.split('-')[0].strip()
                                    ipo_id = f"sec_{company}_{published}"

                                    if ipo_id not in self.seen_ipos:
                                        ipos.append({
                                            'company': company,
                                            'cik': '',
                                            'filing_date': published,
                                            'type': 'SEC S-1 Filing',
                                            'source': 'SEC EDGAR',
                                            'sec_url': 'https://www.sec.gov/cgi-bin/browse-edgar?type=S-1'
                                        })
                                        self.seen_ipos.add(ipo_id)
                        except:
                            continue

                except:
                    pass

        except Exception as e:
            print(f"Error with SEC RSS backup: {e}")

        return ipos

    def format_ipo_alert(self, ipo: Dict) -> str:
        """Format an IPO into readable alert text"""
        company = ipo.get('company', 'Unknown')
        filing_date = ipo.get('filing_date', 'Unknown')
        ipo_type = ipo.get('type', 'IPO')
        source = ipo.get('source', 'Finance Data')
        price_range = ipo.get('price_range', '')

        alert = f"🚀 NEW IPO ALERT\nCompany: {company}\nDate: {filing_date}\nType: {ipo_type}\nSource: {source}"
        if price_range:
            alert += f"\nPrice Range: {price_range}"
        if ipo.get('sec_url'):
            alert += f"\nLink: {ipo['sec_url']}"
        alert += "\n---"

        return alert
