"""
Email utility for sending transactional emails (e.g. password-reset links).

Reads SMTP settings from environment variables.  When SMTP_HOST is not
configured the email body is logged to the console instead — handy for
local development / testing.
"""

import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "noreply@blendercollab.com")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


def send_password_reset_email(to_email: str, reset_token: str) -> None:
    """
    Send (or log) a password-reset email containing a one-time link.
    """
    reset_link = f"{FRONTEND_URL}/login/reset-password?token={reset_token}"

    subject = "Blender Collab – Password Reset"
    html_body = f"""\
<html>
<body style="font-family:sans-serif;color:#334155;">
  <h2>Password Reset</h2>
  <p>We received a request to reset your password. Click the link below to
  choose a new password. This link expires in 15 minutes.</p>
  <p><a href="{reset_link}" style="color:#0284c7;">Reset my password</a></p>
  <p style="font-size:0.85em;color:#64748b;">
    If you didn't request this, you can safely ignore this email.
  </p>
</body>
</html>"""

    text_body = (
        "Password Reset\n\n"
        "We received a request to reset your password.\n"
        f"Visit this link to choose a new password (expires in 15 min):\n\n{reset_link}\n\n"
        "If you didn't request this, you can safely ignore this email.\n"
    )

    # ---------- If SMTP is not configured, print to console ----------
    if not SMTP_HOST:
        print("\n" + "=" * 60)
        print("  PASSWORD RESET (SMTP not configured)")
        print("=" * 60)
        print(f"  To:   {to_email}")
        print(f"  Link: {reset_link}")
        print("=" * 60 + "\n")
        logger.info("SMTP not configured – reset link printed to console for %s", to_email)
        return

    # ---------- Send via SMTP ----------
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            if SMTP_USER and SMTP_PASSWORD:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, [to_email], msg.as_string())
        logger.info("Password-reset email sent to %s", to_email)
    except Exception as e:
        logger.error("Failed to send reset email to %s: %s", to_email, e)
        # Don't re-raise – caller should still return a generic success to the client

