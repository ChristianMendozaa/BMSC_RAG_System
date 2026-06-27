from dataclasses import dataclass

from app.emails.renderer import BRAND_NAME, escape, render_html_email, render_template


@dataclass(frozen=True)
class EmailContent:
    subject: str
    body_html: str
    body_plain: str


def _build_email(
    subject: str,
    html_template: str,
    plain_template: str,
    html_context: dict[str, object],
    plain_context: dict[str, object] | None = None,
) -> EmailContent:
    html_body = render_template(html_template, html_context)
    plain_body = render_template(plain_template, plain_context or html_context)
    return EmailContent(
        subject=subject,
        body_html=render_html_email(subject, html_body),
        body_plain=plain_body,
    )


def build_verification_code_email(
    username: str,
    code: str,
    expires_minutes: int = 15,
) -> EmailContent:
    subject = f"{BRAND_NAME} | Código de verificación"
    return _build_email(
        subject=subject,
        html_template="first_login_code.html",
        plain_template="first_login_code.txt",
        html_context={
            "username": escape(username),
            "code": escape(code),
            "expires_minutes": expires_minutes,
        },
        plain_context={
            "username": username,
            "code": code,
            "expires_minutes": expires_minutes,
        },
    )


def build_account_created_email(
    to_addr: str,
    username: str,
    temporary_password: str,
    role_name: str | None = None,
) -> EmailContent:
    subject = f"{BRAND_NAME} | Tu cuenta ha sido creada"
    role_section = ""
    role_plain = ""
    if role_name:
        role_section = render_template(
            "partials/value_row.html",
            {
                "label": "Rol asignado",
                "value": escape(role_name),
            },
        )
        role_plain = f"Rol: {role_name}\n"

    return _build_email(
        subject=subject,
        html_template="account_created.html",
        plain_template="account_created.txt",
        html_context={
            "username": escape(username),
            "to_addr": escape(to_addr),
            "temporary_password": escape(temporary_password),
            "role_section": role_section,
        },
        plain_context={
            "username": username,
            "to_addr": to_addr,
            "temporary_password": temporary_password,
            "role_plain": role_plain,
        },
    )


def build_password_reset_email(
    to_addr: str,
    username: str,
    reset_by: str,
    temporary_password: str,
) -> EmailContent:
    subject = f"{BRAND_NAME} | Tu contraseña fue restablecida"
    return _build_email(
        subject=subject,
        html_template="password_reset_admin.html",
        plain_template="password_reset_admin.txt",
        html_context={
            "username": escape(username),
            "to_addr": escape(to_addr),
            "reset_by": escape(reset_by),
            "temporary_password": escape(temporary_password),
        },
        plain_context={
            "username": username,
            "to_addr": to_addr,
            "reset_by": reset_by,
            "temporary_password": temporary_password,
        },
    )


def build_password_reset_code_email(
    username: str,
    code: str,
    expires_minutes: int = 15,
) -> EmailContent:
    subject = f"{BRAND_NAME} | Código para recuperar tu contraseña"
    return _build_email(
        subject=subject,
        html_template="password_reset_code.html",
        plain_template="password_reset_code.txt",
        html_context={
            "username": escape(username),
            "code": escape(code),
            "expires_minutes": expires_minutes,
        },
        plain_context={
            "username": username,
            "code": code,
            "expires_minutes": expires_minutes,
        },
    )


def build_account_locked_email(
    username: str,
    lockout_minutes: int,
) -> EmailContent:
    subject = f"{BRAND_NAME} | Cuenta bloqueada temporalmente"
    return _build_email(
        subject=subject,
        html_template="account_locked.html",
        plain_template="account_locked.txt",
        html_context={
            "username": escape(username),
            "lockout_minutes": lockout_minutes,
        },
        plain_context={
            "username": username,
            "lockout_minutes": lockout_minutes,
        },
    )
