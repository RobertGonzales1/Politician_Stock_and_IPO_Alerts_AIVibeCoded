import requests
import json
from datetime import datetime
from typing import List, Dict
from bs4 import BeautifulSoup

class IPOTracker:
    def __init__(self):
        self.ipo_calendar_api = "https://api.example.com/ipos"
        self.sec_api = "https://data.sec.gov/submissions/CIK"
        self.seen_ipos_file = "data/seen_ipos.json"
        self.seen_ipos = self._load_seen_ipos()

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
        """Fetch upcoming IPOs from various sources"""
        ipos = []

        try:
            response = requests.get(
                "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=424B4&dateb=&owner=exclude&count=100",
                timeout=10,
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')
            table = soup.find('table', {'class': 'tableFile'})

            if table:
                rows = table.find_all('tr')[1:]
                for row in rows[:20]:
                    cols = row.find_all('td')
                    if len(cols) >= 4:
                        company = cols[0].text.strip()
                        cik = cols[1].text.strip()
                        filing_date = cols[3].text.strip()

                        ipo_id = f"{cik}_{filing_date}"
                        if ipo_id not in self.seen_ipos:
                            ipos.append({
                                'company': company,
                                'cik': cik,
                                'filing_date': filing_date,
                                'type': '424B4'
                            })
                            self.seen_ipos.add(ipo_id)

            self._save_seen_ipos()
            return ipos
        except requests.RequestException as e:
            print(f"Error fetching IPO data: {e}")
            return []

    def format_ipo_alert(self, ipo: Dict) -> str:
        """Format an IPO into readable alert text"""
        company = ipo.get('company', 'Unknown')
        filing_date = ipo.get('filing_date', 'Unknown')
        cik = ipo.get('cik', 'Unknown')

        return f"🚀 NEW IPO ALERT\nCompany: {company}\nFiling Date: {filing_date}\nSEC Link: https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=424B4"
