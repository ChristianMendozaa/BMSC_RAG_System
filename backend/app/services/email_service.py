"""
email_service.py
================
Servicio de notificaciones por correo electrónico.

Configuración del relay bancario (sin TLS, sin AUTH):
  SMTP_HOST  = 172.16.17.171
  SMTP_PORT  = 25
  SMTP_FROM  = noreply@banco.com

El envío se ejecuta en un thread separado (run_in_executor) para no
bloquear el event loop de FastAPI.  Los errores se loguean pero nunca
propagan una excepción al llamador: el email es best-effort.
"""

import asyncio
import email.utils
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import partial

from app.config import settings

logger = logging.getLogger(__name__)


# ─── Envío base ───────────────────────────────────────────────────────────────

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
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = email.utils.formataddr(("BMSC Sistema", settings.smtp_from))
    msg["To"] = to_addr
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["X-Mailer"] = "BMSC-RAG/2.0"

    msg.attach(MIMEText(body_plain, "plain", "utf-8"))
    msg.attach(MIMEText(body_html,  "html",  "utf-8"))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout) as s:
        s.ehlo()
        s.sendmail(settings.smtp_from, [to_addr], msg.as_bytes())

    logger.info("[email] Enviado a %s — Asunto: %s", to_addr, subject)


async def send_email(to_addr: str, subject: str, body_html: str, body_plain: str) -> None:
    """
    Wrapper async: ejecuta el envío SMTP en el thread pool para no
    bloquear el event loop.  Los errores se loguan como WARNING.
    Si settings.smtp_enabled=False, solo loguea (modo dry-run para dev/staging).
    """
    if not settings.smtp_enabled:
        logger.info("[email] smtp_enabled=False — email NO enviado a %s | %s", to_addr, subject)
        return

    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(
            None,
            partial(_send_sync, to_addr, subject, body_html, body_plain),
        )
    except smtplib.SMTPException as exc:
        logger.warning("[email] Error SMTP al enviar a %s: %s", to_addr, exc)
    except OSError as exc:
        logger.warning("[email] Error de red al enviar a %s: %s", to_addr, exc)


# ─── Plantillas HTML ──────────────────────────────────────────────────────────

_BASE_STYLE = """
  font-family: Arial, Helvetica, sans-serif;
  background: #f5f6fa;
  margin: 0; padding: 0;
"""

_CARD_STYLE = """
  background: #ffffff;
  max-width: 560px;
  margin: 32px auto;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0,0,0,.08);
"""

_HEADER_STYLE = """
  background: #003366;
  padding: 24px 32px;
  color: #ffffff;
"""

_BODY_STYLE = "padding: 32px;"
_FOOTER_STYLE = "padding: 16px 32px; background:#f5f6fa; font-size:11px; color:#888; text-align:center;"

_LABEL_STYLE = "color:#555; font-size:13px; margin:0 0 2px 0;"
_VALUE_STYLE = (
    "background:#f0f4ff; border-radius:4px; padding:8px 14px; "
    "font-size:15px; font-family:monospace; color:#003366; margin:0 0 16px 0;"
)
_WARN_STYLE = (
    "background:#fff3cd; border-left:4px solid #e6a817; "
    "border-radius:4px; padding:10px 14px; font-size:13px; color:#6d4f00; margin-top:16px;"
)
_NOTE_STYLE = (
    "background:#e8f4fd; border-left:4px solid #0077cc; "
    "border-radius:4px; padding:10px 14px; font-size:13px; color:#004d80; margin-top:16px;"
)


def _wrap_template(title: str, content: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><title>{title}</title></head>
<body style="{_BASE_STYLE}">
  <div style="{_CARD_STYLE}">
    <div style="{_HEADER_STYLE}">
      <h1 style="margin:0;font-size:20px;font-weight:700;letter-spacing:.5px;">
        BMSC · Sistema de Documentación
      </h1>
      <p style="margin:4px 0 0;font-size:13px;opacity:.8;">{title}</p>
    </div>
    <div style="{_BODY_STYLE}">
      {content}
    </div>
    <div style="{_FOOTER_STYLE}">
      Este mensaje fue generado automáticamente. No responda a este correo.<br>
      &copy; Banco Mercantil Santa Cruz · Sistema RAG Interno
    </div>
  </div>
</body>
</html>"""


# ─── Notificación: código de verificación (primer login) ──────────────────────

async def notify_verification_code(
    to_addr: str,
    username: str,
    code: str,
) -> None:
    """
    Envía un código de verificación de 6 dígitos requerido para cambiar
    la contraseña en el primer inicio de sesión.
    """
    subject = "Código de verificación - BMSC"

    html_content = f"""
      <p style="font-size:15px;color:#222;">Hola, <strong>{username}</strong>.</p>
      <p style="color:#555;font-size:14px;">
        Este es tu código de verificación para completar el cambio de contraseña:
      </p>
      <div style="text-align:center; margin:24px 0;">
        <span style="background:#003366; color:#fff; padding:12px 24px; font-size:24px; font-weight:bold; letter-spacing:4px; border-radius:6px; display:inline-block;">
          {code}
        </span>
      </div>
      <p style="color:#555;font-size:14px;text-align:center;">
        El código expirará en 15 minutos.
      </p>
      <div style="{_WARN_STYLE}">
        <strong>&#9888; Importante:</strong> No compartas este código con nadie.
        Ningún administrador te solicitará este código.
      </div>
    """

    plain = (
        f"Hola {username},\n\n"
        f"Tu código de verificación para cambiar tu contraseña es:\n\n"
        f"    {code}\n\n"
        "Este código expira en 15 minutos.\n"
        "Si no solicitaste este código, ignora este mensaje.\n\n"
        "Este mensaje es automático. No respondas a este correo.\n"
    )

    await send_email(to_addr, subject, _wrap_template(subject, html_content), plain)


# ─── Notificación: cuenta creada ──────────────────────────────────────────────

async def notify_account_created(
    to_addr: str,
    username: str,
    temp_password: str,
    role_name: str | None = None,
) -> None:
    """
    Notifica al nuevo usuario que su cuenta fue creada y le entrega
    sus credenciales iniciales.
    """
    subject = "Tu cuenta en BMSC ha sido creada"
    role_line = f"<p style='{_LABEL_STYLE}'>Rol asignado</p><p style='{_VALUE_STYLE}'>{role_name}</p>" if role_name else ""

    html_content = f"""
      <p style="font-size:15px;color:#222;">Hola, <strong>{username}</strong>.</p>
      <p style="color:#555;font-size:14px;">
        Tu cuenta en el sistema de gestión documental del banco ha sido creada.
        A continuación tus credenciales de acceso:
      </p>
      <p style="{_LABEL_STYLE}">Correo / usuario</p>
      <p style="{_VALUE_STYLE}">{to_addr}</p>
      <p style="{_LABEL_STYLE}">Contraseña temporal</p>
      <p style="{_VALUE_STYLE}">{temp_password}</p>
      {role_line}
      <div style="{_WARN_STYLE}">
        <strong>&#9888; Importante:</strong> Comunica esta contraseña solo al usuario.
        Se recomienda cambiarla en el primer inicio de sesión.
      </div>
    """

    plain = (
        f"Hola {username},\n\n"
        f"Tu cuenta en BMSC fue creada.\n"
        f"Usuario: {to_addr}\n"
        f"Contraseña temporal: {temp_password}\n"
        + (f"Rol: {role_name}\n" if role_name else "")
        + "\nCambia tu contraseña al iniciar sesión.\n"
        "\nEste mensaje es automático. No respondas a este correo.\n"
    )

    await send_email(to_addr, subject, _wrap_template(subject, html_content), plain)


# ─── Notificación: contraseña reseteada ───────────────────────────────────────

async def notify_password_reset(
    to_addr: str,
    username: str,
    new_password: str,
    reset_by: str,
) -> None:
    """
    Notifica al usuario que un administrador reseteó su contraseña.
    """
    subject = "Tu contraseña en BMSC fue restablecida"

    html_content = f"""
      <p style="font-size:15px;color:#222;">Hola, <strong>{username}</strong>.</p>
      <p style="color:#555;font-size:14px;">
        Un administrador (<strong>{reset_by}</strong>) ha restablecido tu contraseña.
        Tus nuevas credenciales son:
      </p>
      <p style="{_LABEL_STYLE}">Correo / usuario</p>
      <p style="{_VALUE_STYLE}">{to_addr}</p>
      <p style="{_LABEL_STYLE}">Nueva contraseña</p>
      <p style="{_VALUE_STYLE}">{new_password}</p>
      <div style="{_WARN_STYLE}">
        <strong>&#9888; Si no solicitaste este cambio</strong>, comunícate de
        inmediato con el administrador del sistema.
      </div>
      <div style="{_NOTE_STYLE}">
        Todas tus sesiones activas han sido cerradas por seguridad.
      </div>
    """

    plain = (
        f"Hola {username},\n\n"
        f"El administrador {reset_by} restableció tu contraseña en BMSC.\n"
        f"Usuario: {to_addr}\n"
        f"Nueva contraseña: {new_password}\n\n"
        "Todas tus sesiones activas fueron cerradas.\n"
        "Si no solicitaste este cambio, contacta al administrador.\n\n"
        "Este mensaje es automático. No respondas a este correo.\n"
    )

    await send_email(to_addr, subject, _wrap_template(subject, html_content), plain)


# ─── Notificación: cuenta bloqueada ───────────────────────────────────────────

async def notify_account_locked(
    to_addr: str,
    username: str,
    lockout_minutes: int,
) -> None:
    """
    Notifica al usuario que su cuenta fue bloqueada por intentos fallidos.
    """
    subject = "Tu cuenta en BMSC ha sido bloqueada temporalmente"

    html_content = f"""
      <p style="font-size:15px;color:#222;">Hola, <strong>{username}</strong>.</p>
      <p style="color:#555;font-size:14px;">
        Tu cuenta ha sido <strong>bloqueada temporalmente</strong> debido a
        múltiples intentos de inicio de sesión fallidos.
      </p>
      <p style="{_LABEL_STYLE}">Duración del bloqueo</p>
      <p style="{_VALUE_STYLE}">{lockout_minutes} minuto(s)</p>
      <div style="{_WARN_STYLE}">
        <strong>&#9888; Si no fuiste tú</strong>, alguien puede estar intentando
        acceder a tu cuenta. Comunícate con el administrador del sistema.
      </div>
      <div style="{_NOTE_STYLE}">
        Tu cuenta se desbloqueará automáticamente transcurrido ese tiempo.
        Si necesitas acceso inmediato, contacta a un administrador.
      </div>
    """

    plain = (
        f"Hola {username},\n\n"
        f"Tu cuenta en BMSC fue bloqueada por {lockout_minutes} minuto(s) "
        "debido a múltiples intentos de inicio de sesión fallidos.\n\n"
        "Si no fuiste tú, contacta al administrador de inmediato.\n"
        "Tu cuenta se desbloqueará automáticamente.\n\n"
        "Este mensaje es automático. No respondas a este correo.\n"
    )

    await send_email(to_addr, subject, _wrap_template(subject, html_content), plain)
