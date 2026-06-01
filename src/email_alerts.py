import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List
import os

class EmailAlerter:
    def __init__(self, recipient_email: str, sender_email: str = None, sender_password: str = None):
        self.recipient = recipient_email
        self.sender = sender_email or os.getenv('EMAIL_ADDRESS')
        self.password = sender_password or os.getenv('EMAIL_PASSWORD')
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 587

    def send_alert(self, subject: str, alerts: List[str]) -> bool:
        """Send email alert with formatted content"""
        if not self.sender or not self.password:
            print("Email credentials not configured. Skipping email send.")
            return False

        try:
            msg = MIMEMultipart()
            msg['From'] = self.sender
            msg['To'] = self.recipient
            msg['Subject'] = subject

            body = self._format_email_body(alerts)
            msg.attach(MIMEText(body, 'plain'))

            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.sender, self.password)
            server.send_message(msg)
            server.quit()

            print(f"Alert email sent to {self.recipient}")
            return True
        except Exception as e:
            print(f"Error sending email: {e}")
            return False

    def _format_email_body(self, alerts: List[str]) -> str:
        """Format alerts into email body"""
        if not alerts:
            return "No new alerts today."

        body = "Daily Stock & IPO Alerts\n"
        body += "=" * 40 + "\n\n"
        body += "\n\n".join(alerts)
        body += "\n\n" + "=" * 40
        body += "\nGitHub: https://github.com/RobertGonzales1/Politician_Stock_and_IPO_Alerts_AIVibeCoded"

        return body
