# Politician Stock and IPO Alerts

Automated alerts for when members of Congress buy/sell stocks and new IPOs become available.

## Features

- **Politician Trade Tracking**: Monitors Senate and House stock disclosures via public APIs
- **IPO Alerts**: Tracks new Initial Public Offerings
- **Email Notifications**: Sends daily alerts to your email
- **Automated**: Runs daily via GitHub Actions

## Setup

1. Clone the repository
2. Set up GitHub Secrets:
   - `EMAIL_ADDRESS`: Your email address
   - `EMAIL_PASSWORD`: Your email app-specific password
3. The workflow runs daily at 9 AM UTC

## Data Sources

- **Politician Trades**: Senate Stock Watcher API, House.gov SOPR filings
- **IPOs**: SEC EDGAR filings, IPO calendar data

## Files

- `src/politician_trades.py`: Scrapes politician trade data
- `src/ipo_alerts.py`: Monitors IPO filings
- `src/email_alerts.py`: Sends email notifications
- `.github/workflows/daily_check.yml`: GitHub Actions workflow
