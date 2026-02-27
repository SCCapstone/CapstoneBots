"""
Email utility for sending transactional emails (e.g. password-reset links).

Reads SMTP settings from environment variables.

**Security note:**  When SMTP_HOST is *not* configured the module will only
print token-bearing links to the console if ``EMAIL_DEBUG=true`` is also
set.  This prevents accidental token leakage in staging/production
environments where logs may be accessible to a wider audience.  If SMTP
is unconfigured and EMAIL_DEBUG is not enabled the send functions will
raise, signalling to the caller that delivery failed (fail-closed).
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

# Only print token-bearing links to stdout when this is explicitly enabled.
# Keeps local dev convenient while preventing accidental leaks elsewhere.
EMAIL_DEBUG = os.getenv("EMAIL_DEBUG", "").lower() in ("true", "1", "yes")


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

    # ---------- If SMTP is not configured ----------
    if not SMTP_HOST:
        if EMAIL_DEBUG:
            print("\n" + "=" * 60)
            print("  PASSWORD RESET (EMAIL_DEBUG mode – SMTP not configured)")
            print("=" * 60)
            print(f"  To:   {to_email}")
            print(f"  Link: {reset_link}")
            print("=" * 60 + "\n")
            logger.info("EMAIL_DEBUG – reset link printed to console for %s", to_email)
            return

        # Fail closed: SMTP is required outside of EMAIL_DEBUG mode.
        logger.error(
            "SMTP_HOST is not configured and EMAIL_DEBUG is not enabled. "
            "Cannot send password-reset email to %s.", to_email,
        )
        raise RuntimeError("Email delivery is not configured. Set SMTP_HOST or enable EMAIL_DEBUG for local development.")

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
        raise


def send_verification_email(to_email: str, verification_token: str) -> None:
    """
    Send (or log) an email-verification email containing a one-time link.
    """
    verify_link = f"{FRONTEND_URL}/verify-email?token={verification_token}"

    subject = "Blender Collab – Verify Your Email"
    html_body = f"""\
<html>
<body style="font-family:sans-serif;color:#334155;">
  <h2>Verify Your Email</h2>
  <p>Thanks for signing up! Please click the link below to verify your
  email address. This link expires in 24 hours.</p>
  <p><a href="{verify_link}" style="color:#0284c7;">Verify my email</a></p>
  <p style="font-size:0.85em;color:#64748b;">
    If you didn't create an account, you can safely ignore this email.
  </p>
</body>
</html>"""

    text_body = (
        "Verify Your Email\n\n"
        "Thanks for signing up!\n"
        f"Visit this link to verify your email (expires in 24 hours):\n\n{verify_link}\n\n"
        "If you didn't create an account, you can safely ignore this email.\n"
    )

    # ---------- If SMTP is not configured ----------
    if not SMTP_HOST:
        if EMAIL_DEBUG:
            print("\n" + "=" * 60)
            print("  EMAIL VERIFICATION (EMAIL_DEBUG mode – SMTP not configured)")
            print("=" * 60)
            print(f"  To:   {to_email}")
            print(f"  Link: {verify_link}")
            print("=" * 60 + "\n")
            logger.info("EMAIL_DEBUG – verification link printed to console for %s", to_email)
            return

        # Fail closed: SMTP is required outside of EMAIL_DEBUG mode.
        logger.error(
            "SMTP_HOST is not configured and EMAIL_DEBUG is not enabled. "
            "Cannot send verification email to %s.", to_email,
        )
        raise RuntimeError("Email delivery is not configured. Set SMTP_HOST or enable EMAIL_DEBUG for local development.")

    # ---------- Send via SMTP ----------
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            if SMTP_USER and SMTP_PASSWORD:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, [to_email], msg.as_string())
        logger.info("Verification email sent to %s", to_email)
    except Exception as e:
        logger.error("Failed to send verification email to %s: %s", to_email, e)
        raise


