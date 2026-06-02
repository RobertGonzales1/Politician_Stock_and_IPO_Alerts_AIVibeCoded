import requests
import json
from datetime import datetime, timedelta
from typing import List, Dict
import time

class IPOTracker:
    def __init__(self):
        self.seen_ipos_file = "data/seen_ipos.json"
        self.seen_ipos = self._load_seen_ipos()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
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
        """Fetch upcoming IPOs using SEC EDGAR JSON API (free, no auth required)"""
        ipos = []

        try:
            # Use SEC EDGAR JSON API to get S-1 filings (IPO registration statements)
            # This is the official SEC API - no authentication needed
            url = "https://www.sec.gov/cgi-json/browse-edgar"
            params = {
                'action': 'getcompany',
                'type': 'S-1',
                'count': 100,
                'output': 'json'
            }

            response = requests.get(url, params=params, headers=self.headers, timeout=15)
            response.raise_for_status()

            data = response.json()
            filings = data.get('filings', {}).get('filing', [])

            # Process S-1 filings (IPO prospectuses)
            for filing in filings[:40]:
                try:
                    company_name = filing.get('company_name', '').strip()
                    cik = filing.get('cik_str', '')
                    filing_date = filing.get('filing_date', '')
                    accession = filing.get('accession_number', '')

                    if company_name and cik and filing_date:
                        ipo_id = f"{cik}_{filing_date}_{company_name}"

                        if ipo_id not in self.seen_ipos:
                            # Get more details if available
                            form_type = filing.get('form_type', 'S-1').strip()

                            ipos.append({
                                'company': company_name,
                                'cik': cik,
                                'filing_date': filing_date,
                                'accession': accession,
                                'type': form_type,
                                'sec_url': f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=S-1&dateb=&owner=exclude&count=100",
                                'filing_url': f"https://www.sec.gov/cgi-bin/viewer?action=view&cik={cik}&accession_number={accession}&xbrl_type=v"
                            })
                            self.seen_ipos.add(ipo_id)

                except (KeyError, TypeError) as e:
                    continue

            # Add delay to be respectful to SEC servers
            time.sleep(1)

            # Also check for 424B5 filings (prospectus supplements - sometimes indicates IPO ready)
            try:
                params['type'] = '424B5'
                response2 = requests.get(url, params=params, headers=self.headers, timeout=15)
                response2.raise_for_status()

                data2 = response2.json()
                filings2 = data2.get('filings', {}).get('filing', [])

                for filing in filings2[:20]:
                    try:
                        company_name = filing.get('company_name', '').strip()
                        cik = filing.get('cik_str', '')
                        filing_date = filing.get('filing_date', '')
                        accession = filing.get('accession_number', '')

                        if company_name and cik:
                            ipo_id = f"{cik}_{filing_date}_{company_name}_424B5"

                            if ipo_id not in self.seen_ipos:
                                ipos.append({
                                    'company': company_name,
                                    'cik': cik,
                                    'filing_date': filing_date,
                                    'accession': accession,
                                    'type': '424B5 (Prospectus Supplement)',
                                    'sec_url': f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&owner=exclude",
                                    'filing_url': f"https://www.sec.gov/cgi-bin/viewer?action=view&cik={cik}&accession_number={accession}&xbrl_type=v"
                                })
                                self.seen_ipos.add(ipo_id)
                    except (KeyError, TypeError):
                        continue

            except:
                pass

            self._save_seen_ipos()
            return ipos[:30]  # Return top 30 IPOs

        except requests.RequestException as e:
            print(f"Error fetching IPO data: {e}")
            return []

    def format_ipo_alert(self, ipo: Dict) -> str:
        """Format an IPO into readable alert text"""
        company = ipo.get('company', 'Unknown')
        filing_date = ipo.get('filing_date', 'Unknown')
        form_type = ipo.get('type', 'S-1')
        sec_url = ipo.get('sec_url', '')

        alert = f"🚀 NEW IPO ALERT\nCompany: {company}\nFiling Date: {filing_date}\nForm Type: {form_type}"
        if sec_url:
            alert += f"\nView on SEC: {sec_url}"
        alert += "\n---"

        return alert
