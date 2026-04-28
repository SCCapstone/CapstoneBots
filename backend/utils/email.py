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
from dataclasses import dataclass
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from functools import lru_cache
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

SMTP_TIMEOUT = 30


@dataclass(frozen=True)
class EmailConfig:
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from: str
    frontend_url: str
    debug: bool


def _validate_frontend_url(raw: str) -> str:
    # Tokens in reset/verify links must land on the real frontend. A misconfigured
    # FRONTEND_URL (trailing `?`, extra path, attacker-controlled host) would cause
    # the token to be appended to the wrong URL and potentially leak. Fail closed
    # rather than send a broken or malicious link.
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        raise RuntimeError(
            f"FRONTEND_URL must use http or https scheme, got {parsed.scheme!r}"
        )
    if not parsed.netloc:
        raise RuntimeError("FRONTEND_URL is missing a host")
    if parsed.query or parsed.fragment or parsed.params:
        raise RuntimeError("FRONTEND_URL must not contain a query string or fragment")
    if parsed.path not in ("", "/"):
        raise RuntimeError(
            f"FRONTEND_URL must not contain a path, got {parsed.path!r}"
        )
    return f"{parsed.scheme}://{parsed.netloc}"


@lru_cache(maxsize=1)
def get_email_config() -> EmailConfig:
    """Read email settings from the environment.

    Cached so repeated sends don't re-read os.environ. Tests that need to
    override env vars should call ``get_email_config.cache_clear()`` after
    patching the environment.
    """
    smtp_user = os.getenv("SMTP_USER", "")
    return EmailConfig(
        smtp_host=os.getenv("SMTP_HOST", ""),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_user=smtp_user,
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        smtp_from=os.getenv("SMTP_FROM", smtp_user or "noreply@blendercollab.com"),
        frontend_url=_validate_frontend_url(os.getenv("FRONTEND_URL", "http://localhost:3000")),
        debug=os.getenv("EMAIL_DEBUG", "").lower() in ("true", "1", "yes"),
    )


def _send_email(to_email: str, subject: str, text_body: str, html_body: str, *, debug_label: str, debug_link: str) -> None:
    """Send an email or, when SMTP is unconfigured, log to console in debug mode.

    Fails closed: raises if SMTP is not configured and EMAIL_DEBUG is disabled.
    """
    cfg = get_email_config()

    if not cfg.smtp_host:
        if cfg.debug:
            print("\n" + "=" * 60)
            print(f"  {debug_label} (EMAIL_DEBUG mode – SMTP not configured)")
            print("=" * 60)
            print(f"  To:   {to_email}")
            print(f"  Link: {debug_link}")
            print("=" * 60 + "\n")
            logger.info("EMAIL_DEBUG – %s link printed to console for %s", debug_label, to_email)
            return

        logger.error(
            "SMTP_HOST is not configured and EMAIL_DEBUG is not enabled. "
            "Cannot send %s email to %s.", debug_label, to_email,
        )
        raise RuntimeError("Email delivery is not configured. Set SMTP_HOST or enable EMAIL_DEBUG for local development.")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg.smtp_from
    msg["To"] = to_email
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=SMTP_TIMEOUT) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            if cfg.smtp_user and cfg.smtp_password:
                server.login(cfg.smtp_user, cfg.smtp_password)
            server.sendmail(cfg.smtp_from, [to_email], msg.as_string())
        logger.info("%s email sent to %s", debug_label, to_email)
    except Exception as e:
        logger.error("Failed to send %s email to %s: %s", debug_label, to_email, e)
        raise


def send_password_reset_email(to_email: str, reset_token: str) -> None:
    """Send (or log) a password-reset email containing a one-time link."""
    reset_link = f"{get_email_config().frontend_url}/login/reset-password?token={reset_token}"

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

    _send_email(
        to_email,
        subject="Blender Collab – Password Reset",
        text_body=text_body,
        html_body=html_body,
        debug_label="PASSWORD RESET",
        debug_link=reset_link,
    )


def send_verification_email(to_email: str, verification_token: str) -> None:
    """Send (or log) an email-verification email containing a one-time link."""
    verify_link = f"{get_email_config().frontend_url}/verify-email?token={verification_token}"

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

    _send_email(
        to_email,
        subject="Blender Collab – Verify Your Email",
        text_body=text_body,
        html_body=html_body,
        debug_label="EMAIL VERIFICATION",
        debug_link=verify_link,
    )
