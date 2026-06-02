import requests
import json
from datetime import datetime, timedelta
from typing import List, Dict
from xml.etree import ElementTree as ET
import time

class IPOTracker:
    def __init__(self):
        self.seen_ipos_file = "data/seen_ipos.json"
        self.seen_ipos = self._load_seen_ipos()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/rss+xml,application/xml,*/*',
            'Referer': 'https://www.sec.gov'
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
        """Fetch IPOs using SEC RSS feeds (designed for automated access)"""
        ipos = []

        try:
            # Use SEC RSS feeds - these are designed for automated consumption
            # CIK = 0 with form type S-1 = all S-1 filings

            # Try the RSS feed for S-1 filings
            rss_urls = [
                "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=S-1&dateb=&owner=exclude&match=&count=100&format=atom",
                "https://www.sec.gov/feeds/form-S1",
                "https://feeds.bloomberg.com/markets/IPO_Calendar.rss"
            ]

            for rss_url in rss_urls:
                try:
                    response = requests.get(rss_url, headers=self.headers, timeout=15)

                    if response.status_code == 200:
                        # Parse RSS/Atom feed
                        root = ET.fromstring(response.content)

                        # Handle both RSS and Atom formats
                        namespaces = {
                            'atom': 'http://www.w3.org/2005/Atom',
                            'content': 'http://purl.org/rss/1.0/modules/content/'
                        }

                        # Try Atom format first
                        entries = root.findall('atom:entry', namespaces)
                        if not entries:
                            entries = root.findall('.//item')

                        for entry in entries[:30]:
                            try:
                                # Atom format
                                title_elem = entry.find('atom:title', namespaces)
                                published_elem = entry.find('atom:published', namespaces)
                                link_elem = entry.find('atom:link', namespaces)

                                # RSS format fallback
                                if title_elem is None:
                                    title_elem = entry.find('title')
                                if published_elem is None:
                                    published_elem = entry.find('pubDate')
                                if link_elem is None:
                                    link_elem = entry.find('link')

                                title = title_elem.text if title_elem is not None else ''
                                date = published_elem.text if published_elem is not None else str(datetime.now().date())
                                link = link_elem.text if link_elem is not None else ''
                                if link_elem is not None and link_elem.get('href'):
                                    link = link_elem.get('href')

                                if 'S-1' in title or 'IPO' in title.upper():
                                    # Extract company name and CIK from title
                                    company_name = title.split('-')[0].strip() if '-' in title else title[:60]
                                    cik = title.split('CIK=')[-1][:10] if 'CIK=' in title else ''

                                    ipo_id = f"{cik}_{company_name}_{date}"

                                    if ipo_id not in self.seen_ipos and company_name:
                                        ipos.append({
                                            'company': company_name,
                                            'cik': cik,
                                            'filing_date': date[:10],
                                            'type': 'S-1 (IPO Registration)',
                                            'sec_url': link if link else f"https://www.sec.gov/cgi-bin/browse-edgar?type=S-1"
                                        })
                                        self.seen_ipos.add(ipo_id)
                            except Exception as e:
                                continue

                        if ipos:  # If we got results from this feed, return
                            break

                    time.sleep(0.5)  # Small delay between requests

                except Exception as e:
                    print(f"Error with RSS feed {rss_url}: {e}")
                    continue

            self._save_seen_ipos()
            return ipos[:25]

        except Exception as e:
            print(f"Error fetching IPO data: {e}")
            return []

    def format_ipo_alert(self, ipo: Dict) -> str:
        """Format an IPO into readable alert text"""
        company = ipo.get('company', 'Unknown')
        filing_date = ipo.get('filing_date', 'Unknown')
        ipo_type = ipo.get('type', 'S-1')
        sec_url = ipo.get('sec_url', '')

        alert = f"🚀 NEW IPO ALERT\nCompany: {company}\nFiling Date: {filing_date}\nType: {ipo_type}"
        if sec_url:
            alert += f"\nLink: {sec_url}"
        alert += "\n---"

        return alert
