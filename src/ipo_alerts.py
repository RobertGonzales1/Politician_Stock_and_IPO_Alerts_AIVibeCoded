import requests
import json
from datetime import datetime, timedelta
from typing import List, Dict
from bs4 import BeautifulSoup
import re

class IPOTracker:
    def __init__(self):
        self.seen_ipos_file = "data/seen_ipos.json"
        self.seen_ipos = self._load_seen_ipos()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5'
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
        """Scrape upcoming IPOs from SEC and financial data sources"""
        ipos = []

        try:
            # Method 1: Try SEC EDGAR with JSON API (less likely to be blocked)
            url = "https://www.sec.gov/cgi-json/browse-edgar?action=getcompany&type=S-1&dateb=&owner=exclude&count=40"

            response = requests.get(url, headers=self.headers, timeout=15)

            if response.status_code == 200:
                try:
                    data = response.json()
                    filings = data.get('filings', {}).get('filing', [])

                    for filing in filings[:25]:
                        company_name = filing.get('company_name', 'Unknown')
                        cik = filing.get('cik_str', '')
                        date = filing.get('filing_date', str(datetime.now().date()))

                        ipo_id = f"{cik}_{company_name}_{date}"

                        if ipo_id not in self.seen_ipos and company_name:
                            ipos.append({
                                'company': company_name,
                                'cik': cik,
                                'filing_date': date,
                                'type': 'S-1 (IPO Registration)',
                                'sec_url': f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&owner=exclude&count=100"
                            })
                            self.seen_ipos.add(ipo_id)
                except json.JSONDecodeError:
                    # If JSON fails, try HTML parsing
                    ipos.extend(self._scrape_html_fallback())
            else:
                # Fallback to HTML scraping
                ipos.extend(self._scrape_html_fallback())

            self._save_seen_ipos()
            return ipos

        except requests.RequestException as e:
            print(f"Error fetching IPO data: {e}")
            return []

    def _scrape_html_fallback(self) -> List[Dict]:
        """Fallback method using HTML scraping"""
        ipos = []
        try:
            # Try alternative SEC URL format
            url = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=424B4&owner=exclude&count=50"
            response = requests.get(url, headers=self.headers, timeout=15)

            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                table = soup.find('table', {'summary': 'Results'})

                if table:
                    rows = table.find_all('tr')[1:26]  # Skip header, get first 25

                    for row in rows:
                        cols = row.find_all('td')
                        if len(cols) >= 4:
                            try:
                                company_link = cols[0].find('a')
                                if company_link:
                                    company = company_link.text.strip()
                                    cik = cols[1].text.strip()
                                    date = cols[3].text.strip()

                                    ipo_id = f"{cik}_{company}_{date}"
                                    if ipo_id not in self.seen_ipos and company:
                                        ipos.append({
                                            'company': company,
                                            'cik': cik,
                                            'filing_date': date,
                                            'type': '424B4 (IPO Prospectus)',
                                            'sec_url': f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&owner=exclude"
                                        })
                                        self.seen_ipos.add(ipo_id)
                            except (IndexError, AttributeError):
                                continue
        except:
            pass

        return ipos

    def format_ipo_alert(self, ipo: Dict) -> str:
        """Format an IPO into readable alert text"""
        company = ipo.get('company', 'Unknown')
        filing_date = ipo.get('filing_date', 'Unknown')
        ipo_type = ipo.get('type', 'S-1 Filing')
        sec_url = ipo.get('sec_url', '')

        alert = f"🚀 NEW IPO ALERT\nCompany: {company}\nFiling Date: {filing_date}\nType: {ipo_type}"
        if sec_url:
            alert += f"\nSEC Link: {sec_url}"
        alert += "\n---"

        return alert
