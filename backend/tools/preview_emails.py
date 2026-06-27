"""Generate local HTML previews for all email templates.

Usage from the repository root:
    python3 backend/tools/preview_emails.py
    python3 backend/tools/preview_emails.py --output /tmp/bmsc_email_previews
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = BACKEND_DIR / "email_previews"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.emails.messages import (  # noqa: E402
    EmailContent,
    build_account_created_email,
    build_account_locked_email,
    build_password_reset_code_email,
    build_password_reset_email,
    build_verification_code_email,
)
from app.emails.renderer import LOGO_CID, LOGO_FILENAME, LOGO_PATH  # noqa: E402


def build_preview_messages() -> dict[str, EmailContent]:
    return {
        "account_created.html": build_account_created_email(
            to_addr="usuario.prueba@bmsc.local",
            username="usuario.prueba",
            temporary_password="Temporal1234",
            role_name="Analista Documental",
        ),
        "first_login_code.html": build_verification_code_email(
            username="usuario.prueba",
            code="123456",
            expires_minutes=15,
        ),
        "password_reset_admin.html": build_password_reset_email(
            to_addr="usuario.prueba@bmsc.local",
            username="usuario.prueba",
            reset_by="admin",
            temporary_password="NuevaTemporal1234",
        ),
        "password_reset_code.html": build_password_reset_code_email(
            username="usuario.prueba",
            code="654321",
            expires_minutes=15,
        ),
        "account_locked.html": build_account_locked_email(
            username="usuario.prueba",
            lockout_minutes=15,
        ),
    }


def write_previews(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    preview_logo = output_dir / LOGO_FILENAME
    if LOGO_PATH.exists():
        shutil.copyfile(LOGO_PATH, preview_logo)

    written: list[Path] = []
    for filename, message in build_preview_messages().items():
        path = output_dir / filename
        html = message.body_html.replace(f"cid:{LOGO_CID}", LOGO_FILENAME)
        path.write_text(html, encoding="utf-8")
        written.append(path)
    return written


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate HTML previews for BMSC email templates.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory for preview HTML files. Default: {DEFAULT_OUTPUT_DIR}",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    written = write_previews(args.output)
    print(f"Generated {len(written)} email preview(s) in {args.output}")
    for path in written:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
