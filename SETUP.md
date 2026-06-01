# Setup Instructions

## GitHub Secrets Configuration

To make this workflow function, you need to set up GitHub Secrets in your repository:

### Steps to Add Secrets

1. Go to your repository on GitHub.com
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret** and add these three secrets:

### Required Secrets

#### `EMAIL_ADDRESS`
- Your Gmail address (e.g., `yourname@gmail.com`)
- This is the account that will send the alert emails

#### `EMAIL_PASSWORD`
- **NOT your Gmail password!** Use an [App-Specific Password](https://support.google.com/accounts/answer/185833)
- Steps to create:
  1. Go to [myaccount.google.com](https://myaccount.google.com)
  2. Click **Security** on the left
  3. Enable **2-Step Verification** if not already done
  4. Search for "App passwords" (appears only if 2FA is enabled)
  5. Select **Mail** and **Windows Computer**
  6. Copy the 16-character password generated
  7. Use this as your `EMAIL_PASSWORD` secret

#### `ALERT_EMAIL`
- The email address where you want to receive alerts (can be the same as `EMAIL_ADDRESS`)

## Testing

You can manually trigger the workflow to test it:

1. Go to your repository → **Actions** tab
2. Select **Daily Stock & IPO Check** workflow
3. Click **Run workflow** → **Run workflow**

Check your email in a few moments!

## Troubleshooting

If you don't receive emails:
1. Check the **Actions** tab for workflow failures
2. Verify all three secrets are set correctly
3. Make sure your Gmail account allows [Less secure app access](https://myaccount.google.com/lesssecureapps) OR use App Passwords (recommended)
