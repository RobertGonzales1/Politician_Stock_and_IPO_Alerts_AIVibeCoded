# Politician Stock and IPO Alerts

Automated daily alerts for when members of Congress buy/sell stocks and new IPOs file with the SEC.

## Features

- **Congressional Trade Tracking**: Monitors Form 4 filings and financial disclosures from House/Senate
- **IPO Alerts**: Tracks S-1 registrations (IPO prospectuses) and 424B5 filings
- **Email Notifications**: Sends daily email alerts with new filings
- **Automated**: Runs daily via GitHub Actions at 9 AM UTC
- **100% Free**: Uses SEC EDGAR JSON API (no authentication, no cost)

## How It Works

The system uses the **official SEC EDGAR JSON API** to:
1. Query recent S-1 and 424B5 filings (IPO registrations)
2. Check Form 4 and Congressional financial disclosures
3. Track which alerts have already been sent (avoid duplicates)
4. Email you only NEW alerts

## Setup

### Required GitHub Secrets

Go to **Settings → Secrets and variables → Actions** and add:

1. **EMAIL_ADDRESS** - Your Gmail address
2. **EMAIL_PASSWORD** - [App-Specific Password](https://support.google.com/accounts/answer/185833) (NOT your regular password)
3. **ALERT_EMAIL** - Where you want alerts sent

### Gmail Setup

If using Gmail:
1. Enable [2-Step Verification](https://myaccount.google.com/security)
2. Generate an [App-Specific Password](https://support.google.com/accounts/answer/185833)
3. Use that password as `EMAIL_PASSWORD` secret

## Manual Testing

1. Go to **Actions** tab in your GitHub repo
2. Select **Daily Stock & IPO Check**
3. Click **Run workflow** → **Run workflow**
4. Check your email in ~1 minute

## Data Sources

- **SEC EDGAR**: Official filings database
  - S-1 filings: IPO registration statements
  - 424B5 filings: Prospectus supplements
  - Form 4 filings: Insider trades
  - Congressional disclosures

## Troubleshooting

**Not receiving emails?**
- Check the **Actions** tab for workflow errors
- Verify all 3 GitHub Secrets are set correctly
- Make sure your email account allows apps to sign in

**Want to modify alerts?**
- Edit `src/politician_trades.py` or `src/ipo_alerts.py` to change how data is fetched
- Update `SETUP.md` for custom instructions

## Free Forever

This uses only free, public data from the SEC. No API keys, no subscriptions, no costs.
