"""
email_service.py
================
Servicio de notificaciones por correo electrónico.

Configuración del relay bancario (sin TLS, sin AUTH) vía variables de entorno:
  SMTP_HOST, SMTP_PORT, SMTP_FROM, SMTP_TIMEOUT, SMTP_ENABLED

El envío se ejecuta en un thread separado (run_in_executor) para no
bloquear el event loop de FastAPI. Los errores se loguean y se reportan
como False al llamador; los endpoints críticos deciden si deben fallar.
"""

import asyncio
import email.utils
import logging
import smtplib
import textwrap
import unicodedata
from email.message import EmailMessage
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import partial

from app.config import settings
from app.emails.renderer import BRAND_NAME, LOGO_CID, LOGO_FILENAME, LOGO_PATH
from app.emails.messages import (
    build_account_created_email,
    build_account_locked_email,
    build_password_reset_code_email,
    build_password_reset_email,
    build_verification_code_email,
)

logger = logging.getLogger(__name__)


# ─── Envío base ───────────────────────────────────────────────────────────────

def _message_id_domain(from_addr: str) -> str | None:
    if "@" not in from_addr:
        return None
    domain = from_addr.rsplit("@", 1)[1].strip()
    return domain or None


def _add_common_headers(msg: MIMEMultipart | EmailMessage, to_addr: str, subject: str) -> None:
    msg["Subject"] = subject
    msg["From"] = email.utils.formataddr((BRAND_NAME, settings.smtp_from))
    msg["To"] = to_addr
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid(domain=_message_id_domain(settings.smtp_from))
    msg["Auto-Submitted"] = "auto-generated"
    msg["X-Mailer"] = "BMSC-Base-de-Conocimiento"


def _to_7bit_text(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")


def _wrap_7bit_body(value: str) -> str:
    lines: list[str] = []
    for line in _to_7bit_text(value).splitlines():
        if not line or line.startswith(" "):
            lines.append(line)
            continue
        lines.extend(textwrap.wrap(line, width=72, break_long_words=False, break_on_hyphens=False) or [""])
    return "\n".join(lines)


def _smtp_email_format() -> str:
    return settings.smtp_email_format.split("#", 1)[0].strip().lower()


def _build_plain_message(
    to_addr: str,
    subject: str,
    body_plain: str,
) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = _to_7bit_text(subject)
    msg["From"] = email.utils.formataddr((BRAND_NAME, settings.smtp_from))
    msg["To"] = to_addr
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg.set_content(_wrap_7bit_body(body_plain).rstrip() + "\n\n", cte="7bit")
    return msg


def _build_mime_message(
    to_addr: str,
    subject: str,
    body_html: str,
    body_plain: str,
) -> MIMEMultipart:
    msg = MIMEMultipart("related")
    _add_common_headers(msg, to_addr, subject)

    alternative = MIMEMultipart("alternative")
    alternative.attach(MIMEText(body_plain, "plain", "utf-8"))
    alternative.attach(MIMEText(body_html, "html", "utf-8"))
    msg.attach(alternative)

    if LOGO_PATH.exists():
        logo = MIMEImage(LOGO_PATH.read_bytes(), _subtype="png")
        logo.add_header("Content-ID", f"<{LOGO_CID}>")
        logo.add_header("Content-Disposition", "inline", filename=LOGO_FILENAME)
        msg.attach(logo)
    else:
        logger.warning("[email] No se encontró el logo inline: %s", LOGO_PATH)

    return msg


def _build_smtp_message(
    to_addr: str,
    subject: str,
    body_html: str,
    body_plain: str,
) -> MIMEMultipart | EmailMessage:
    email_format = _smtp_email_format()
    if email_format == "plain":
        return _build_plain_message(to_addr, subject, body_plain)
    if email_format != "html":
        logger.warning("[email] SMTP_EMAIL_FORMAT inválido: %s. Usando html.", settings.smtp_email_format)
    return _build_mime_message(to_addr, subject, body_html, body_plain)


def _send_sync(
    to_addr: str,
    subject: str,
    body_html: str,
    body_plain: str,
) -> None:
    """
    Envía un email de forma síncrona (se llama desde un thread del executor).
    Usa SMTP plano en el puerto 25 sin TLS ni autenticación.
    """
    msg = _build_smtp_message(to_addr, subject, body_html, body_plain)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout) as s:
        s.ehlo()
        s.send_message(msg, from_addr=settings.smtp_from, to_addrs=[to_addr])

    logger.info("[email] Enviado a %s — Asunto: %s", to_addr, subject)


async def send_email(to_addr: str, subject: str, body_html: str, body_plain: str) -> bool:
    """
    Wrapper async: ejecuta el envío SMTP en el thread pool para no
    bloquear el event loop.  Los errores se loguan como WARNING.
    Si settings.smtp_enabled=False, solo loguea (modo dry-run para dev/staging).
    """
    if not settings.smtp_enabled:
        logger.info("[email] smtp_enabled=False — email NO enviado a %s | %s", to_addr, subject)
        return True
    if not settings.smtp_host or not settings.smtp_from:
        logger.warning("[email] SMTP habilitado pero falta SMTP_HOST o SMTP_FROM")
        return False

    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(
            None,
            partial(_send_sync, to_addr, subject, body_html, body_plain),
        )
        return True
    except smtplib.SMTPException as exc:
        logger.warning("[email] Error SMTP al enviar a %s: %s", to_addr, exc)
    except OSError as exc:
        logger.warning("[email] Error de red al enviar a %s: %s", to_addr, exc)
    return False


# ─── Notificación: código de verificación (primer login) ──────────────────────

async def notify_verification_code(
    to_addr: str,
    username: str,
    code: str,
    expires_minutes: int = 15,
) -> bool:
    """
    Envía un código de verificación de 6 dígitos requerido para cambiar
    la contraseña en el primer inicio de sesión.
    """
    email = build_verification_code_email(username, code, expires_minutes)
    return await send_email(to_addr, email.subject, email.body_html, email.body_plain)


# ─── Notificación: cuenta creada ──────────────────────────────────────────────

async def notify_account_created(
    to_addr: str,
    username: str,
    temporary_password: str,
    role_name: str | None = None,
) -> bool:
    """
    Notifica al nuevo usuario que su cuenta fue creada y le entrega
    su usuario de acceso junto con la contraseña temporal.
    """
    email = build_account_created_email(to_addr, username, temporary_password, role_name)
    return await send_email(to_addr, email.subject, email.body_html, email.body_plain)


# ─── Notificación: contraseña reseteada ───────────────────────────────────────

async def notify_password_reset(
    to_addr: str,
    username: str,
    reset_by: str,
    temporary_password: str,
) -> bool:
    """
    Notifica al usuario que un administrador reseteó su contraseña.
    """
    email = build_password_reset_email(to_addr, username, reset_by, temporary_password)
    return await send_email(to_addr, email.subject, email.body_html, email.body_plain)


async def notify_password_reset_code(
    to_addr: str,
    username: str,
    code: str,
    expires_minutes: int = 15,
) -> bool:
    """Envía un código de un solo uso para recuperación autoservicio."""
    email = build_password_reset_code_email(username, code, expires_minutes)
    return await send_email(to_addr, email.subject, email.body_html, email.body_plain)


# ─── Notificación: cuenta bloqueada ───────────────────────────────────────────

async def notify_account_locked(
    to_addr: str,
    username: str,
    lockout_minutes: int,
) -> bool:
    """
    Notifica al usuario que su cuenta fue bloqueada por intentos fallidos.
    """
    email = build_account_locked_email(username, lockout_minutes)
    return await send_email(to_addr, email.subject, email.body_html, email.body_plain)
