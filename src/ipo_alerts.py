import requests
import json
from datetime import datetime
from typing import List, Dict
from bs4 import BeautifulSoup
import re

class IPOTracker:
    def __init__(self):
        self.seen_ipos_file = "data/seen_ipos.json"
        self.seen_ipos = self._load_seen_ipos()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
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
        """Scrape upcoming IPOs from SEC EDGAR and other sources"""
        ipos = []

        try:
            # Method 1: SEC EDGAR - Recent S-1 filings (IPO prospectuses)
            url = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=S-1&dateb=&owner=exclude&count=100&myHID="
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Find the main results table
            table = soup.find('table', {'class': 'tableFile'})

            if table:
                rows = table.find_all('tr')[1:]  # Skip header

                for row in rows[:25]:  # Limit to first 25 results
                    try:
                        cols = row.find_all('td')
                        if len(cols) >= 4:
                            company_link = cols[0].find('a')
                            if company_link:
                                company = company_link.text.strip()
                                cik = cols[1].text.strip()
                                filing_date = cols[3].text.strip()

                                # Create unique ID
                                ipo_id = f"{cik}_{filing_date}_{company}"

                                if ipo_id not in self.seen_ipos and company:
                                    ipos.append({
                                        'company': company,
                                        'cik': cik,
                                        'filing_date': filing_date,
                                        'type': 'S-1 (IPO Prospectus)',
                                        'sec_url': f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=S-1&dateb=&owner=exclude&count=100"
                                    })
                                    self.seen_ipos.add(ipo_id)
                    except (IndexError, AttributeError) as e:
                        continue

            self._save_seen_ipos()
            return ipos

        except requests.RequestException as e:
            print(f"Error fetching IPO data: {e}")
            return []

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
