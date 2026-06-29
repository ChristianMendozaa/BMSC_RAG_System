"""Manual SMTP relay check.

This script is intentionally standalone and is not collected by pytest. Run it
from the project root or from the backend folder to verify that backend/.env has
working SMTP settings and that the relay accepts the configured sender.

Examples:
    python3 backend/tests/smtp_email_check.py --to user@example.com
    python3 tests/smtp_email_check.py --to user@example.com --dry-run

By default the script performs the SMTP handshake, MAIL FROM, RCPT TO and sends
a small test email. Use --dry-run to skip DATA/send_message.
"""

from __future__ import annotations

import argparse
import email.utils
import os
import smtplib
import socket
import sys
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = BACKEND_DIR / ".env"


def load_env_file(path: Path = ENV_PATH) -> None:
    if not path.exists():
        raise SystemExit(f"Missing env file: {path}")

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_smtp_settings() -> tuple[str, int, str, int, bool, str]:
    load_env_file()
    host = os.getenv("SMTP_HOST", "").strip()
    port_raw = os.getenv("SMTP_PORT", "25").strip()
    from_addr = os.getenv("SMTP_FROM", "").strip()
    timeout_raw = os.getenv("SMTP_TIMEOUT", "10").strip()
    enabled = os.getenv("SMTP_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
    email_format = os.getenv("SMTP_EMAIL_FORMAT", "html").split("#", 1)[0].strip().lower()

    missing = [name for name, value in (("SMTP_HOST", host), ("SMTP_FROM", from_addr)) if not value]
    if missing:
        raise SystemExit(f"Missing required SMTP setting(s): {', '.join(missing)}")

    try:
        port = int(port_raw)
        timeout = int(timeout_raw)
    except ValueError as exc:
        raise SystemExit("SMTP_PORT and SMTP_TIMEOUT must be integers") from exc

    if email_format not in {"plain", "html"}:
        raise SystemExit("SMTP_EMAIL_FORMAT must be plain or html")

    return host, port, from_addr, timeout, enabled, email_format


def build_plain_message(from_addr: str, to_addr: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = "BMSC Base de Conocimiento | Prueba SMTP"
    msg["From"] = email.utils.formataddr(("BMSC Base de Conocimiento", from_addr))
    msg["To"] = to_addr
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg.set_content(
        "Este es un correo de prueba enviado por BMSC Base de Conocimiento.\n"
        "Si lo recibiste, SMTP_HOST, SMTP_PORT y SMTP_FROM estan funcionando.\n"
        "\n"
    )
    return msg


def build_html_message(from_addr: str, to_addr: str) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "BMSC Base de Conocimiento | Prueba SMTP"
    msg["From"] = email.utils.formataddr(("BMSC Base de Conocimiento", from_addr))
    msg["To"] = to_addr
    msg["Date"] = email.utils.formatdate(localtime=True)
    plain = (
        "Este es un correo de prueba HTML enviado por BMSC Base de Conocimiento.\n"
        "Si lo recibiste, el relay acepta multipart/alternative.\n\n"
    )
    html = """\
<!DOCTYPE html>
<html>
  <body>
    <p>Este es un correo de prueba HTML enviado por BMSC Base de Conocimiento.</p>
    <p>Si lo recibiste, el relay acepta multipart/alternative.</p>
  </body>
</html>
"""
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    return msg


def build_message(from_addr: str, to_addr: str, email_format: str) -> EmailMessage | MIMEMultipart:
    if email_format == "plain":
        return build_plain_message(from_addr, to_addr)
    return build_html_message(from_addr, to_addr)


def run_relay_check(to_addr: str, dry_run: bool) -> int:
    host, port, from_addr, timeout, enabled, email_format = get_smtp_settings()

    print("SMTP relay check")
    print(f"  env file     : {ENV_PATH}")
    print(f"  SMTP_HOST    : {host}")
    print(f"  SMTP_PORT    : {port}")
    print(f"  SMTP_FROM    : {from_addr}")
    print(f"  SMTP_ENABLED : {enabled}")
    print(f"  EMAIL_FORMAT : {email_format}")
    print(f"  recipient    : {to_addr}")
    print(f"  dry run      : {dry_run}")
    print()

    if not enabled:
        print("FAIL: SMTP_ENABLED is false. Set SMTP_ENABLED=true to test the real relay.")
        return 2

    try:
        with smtplib.SMTP(host, port, timeout=timeout) as smtp:
            code, banner = smtp.ehlo()
            banner_text = banner.decode(errors="replace") if isinstance(banner, bytes) else str(banner)
            print(f"EHLO: {code} {banner_text}")

            features = smtp.esmtp_features
            if "starttls" in features:
                print("WARN: relay advertises STARTTLS, but the app is configured for plain SMTP.")
            if "auth" in features:
                print("WARN: relay advertises AUTH, but the app does not authenticate.")

            code, response = smtp.mail(from_addr)
            response_text = response.decode(errors="replace") if isinstance(response, bytes) else str(response)
            print(f"MAIL FROM: {code} {response_text}")
            if code != 250:
                print("FAIL: relay rejected SMTP_FROM.")
                return 3

            code, response = smtp.rcpt(to_addr)
            response_text = response.decode(errors="replace") if isinstance(response, bytes) else str(response)
            print(f"RCPT TO: {code} {response_text}")
            if code not in {250, 251}:
                print("FAIL: relay rejected the recipient. External mail may be blocked.")
                return 4

            if dry_run:
                print("OK: handshake, sender and recipient checks passed. Email was not sent.")
                return 0

            smtp.rset()
            msg = build_message(from_addr, to_addr, email_format)
            refused = smtp.send_message(msg, from_addr=from_addr, to_addrs=[to_addr])
            if refused:
                print(f"FAIL: relay refused recipients during DATA/send: {refused}")
                return 5

            print("OK: test email sent. Check the recipient inbox and spam folder.")
            return 0
    except (smtplib.SMTPException, OSError, socket.timeout) as exc:
        print(f"FAIL: SMTP check failed: {exc}")
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check SMTP relay settings from backend/.env")
    parser.add_argument("--to", required=True, help="Recipient email address for the test")
    parser.add_argument("--dry-run", action="store_true", help="Check SMTP envelope without sending DATA")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sys.exit(run_relay_check(args.to, args.dry_run))
