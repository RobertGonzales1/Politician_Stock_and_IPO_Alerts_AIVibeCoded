# Politician Stock and IPO Alerts

Automated daily email alerts for congressional stock trades and new IPO filings.

## Features

- **Congressional Trade Tracking**: Official House Clerk STOCK Act disclosures
  (Periodic Transaction Reports) with real tickers, buy/sell action, amount
  ranges, trade dates, and disclosure dates
- **IPO Alerts**: Tracks S-1 registrations and prospectus filings
- **News Supplement**: Google News articles about Congress trading that name a
  specific ticker
- **Email Notifications**: Clean daily digest
- **Automated**: Runs daily at 9 AM UTC via GitHub Actions

## Data Sources (and why)

Members of Congress do **not** file SEC Form 4s — those are for corporate
insiders. Congressional trades are disclosed under the STOCK Act to the House
and Senate Clerks:

- **House trades (primary)**: [house-stock-watcher-data](https://github.com/TattooedHead/house-stock-watcher-data)
  — a maintained JSON mirror of the official filings at
  [disclosures-clerk.house.gov](https://disclosures-clerk.house.gov/FinancialDisclosure)
- **Senate trades**: no maintained free JSON mirror currently exists (the
  senate-stock-watcher project stopped updating in 2020), so Senate coverage
  comes via the news feed
- **News supplement**: Google News RSS (only articles naming a ticker)
- **IPOs**: SEC EDGAR filings

## Alert Format

```
Gilbert Cisneros (CA31)
BUY 📈 MELI  ($15,001 - $50,000)
Traded: 06/10/2026 | Disclosed: 07/02/2026
Source: House PTR
---
```

Note: STOCK Act filings allow up to 45 days between a trade and its disclosure,
so alerts fire when a trade becomes *public*, which can lag the trade itself.

## Setup

### Required GitHub Secrets

Go to **Settings → Secrets and variables → Actions** and add:

1. **EMAIL_ADDRESS** — Gmail address that sends the alerts
2. **EMAIL_PASSWORD** — a Gmail [App-Specific Password](https://support.google.com/accounts/answer/185833) (not your regular password)
3. **ALERT_EMAIL** — where to send alerts

Also enable **Settings → Actions → General → Workflow permissions → Read and
write permissions** so the workflow can persist its dedup tracking data.

## Manual Testing

1. Go to the **Actions** tab
2. Select **Daily Stock & IPO Check**
3. Click **Run workflow**
4. Check your email in ~1 minute

## Files

- `src/politician_trades.py` — congressional trade tracking
- `src/ipo_alerts.py` — IPO filing tracking
- `src/email_alerts.py` — email delivery
- `src/main.py` — orchestrator
- `src/data/` — dedup state (auto-committed by the workflow)
- `.github/workflows/daily_check.yml` — daily schedule
