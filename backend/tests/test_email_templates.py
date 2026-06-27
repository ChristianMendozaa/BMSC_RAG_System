from app.emails.messages import (
    build_account_created_email,
    build_account_locked_email,
    build_password_reset_code_email,
    build_password_reset_email,
    build_verification_code_email,
)
from app.emails.renderer import BRAND_NAME, LOGO_CID
from app.services import email_service
from app.services.email_service import _build_mime_message


FORBIDDEN_BRAND_TERMS = (
    "Sistema de Documentación",
    "Sistema RAG",
    "RAG Interno",
    "gestión documental",
    "BMSC-RAG",
)


def test_all_email_templates_render_subject_html_and_plain():
    emails = [
        build_account_created_email(
            to_addr="usuario@bmsc.local",
            username="usuario",
            temporary_password="Temporal1234",
            role_name="Analista",
        ),
        build_verification_code_email("usuario", "123456", 15),
        build_password_reset_email("usuario@bmsc.local", "usuario", "admin", "NuevaTemporal1234"),
        build_password_reset_code_email("usuario", "654321", 15),
        build_account_locked_email("usuario", 15),
    ]

    for email in emails:
        assert email.subject
        assert "<!DOCTYPE html>" in email.body_html
        assert BRAND_NAME in email.subject
        assert BRAND_NAME in email.body_html
        assert BRAND_NAME in email.body_plain
        assert f"cid:{LOGO_CID}" in email.body_html
        assert "$" not in email.body_html
        assert "$" not in email.body_plain
        for forbidden in FORBIDDEN_BRAND_TERMS:
            assert forbidden not in email.subject
            assert forbidden not in email.body_html
            assert forbidden not in email.body_plain


def test_admin_password_reset_email_includes_temporary_password():
    email = build_password_reset_email(
        to_addr="usuario@bmsc.local",
        username="usuario",
        reset_by="admin",
        temporary_password="NuevaTemporal1234",
    )

    assert "NuevaTemporal1234" in email.body_html
    assert "NuevaTemporal1234" in email.body_plain
    assert "Contraseña temporal" in email.body_html
    assert "Contraseña temporal" in email.body_plain


def test_email_templates_escape_html_values():
    email = build_password_reset_email(
        to_addr="usuario@example.com",
        username="<script>alert(1)</script>",
        reset_by="admin",
        temporary_password="Temporal<123>",
    )

    assert "<script>" not in email.body_html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in email.body_html
    assert "Temporal&lt;123&gt;" in email.body_html


def test_email_mime_message_includes_plain_html_and_inline_logo(monkeypatch):
    monkeypatch.setattr(email_service.settings, "smtp_from", "no-reply@bmsc.com.bo")
    email = build_password_reset_code_email("usuario", "654321", 15)

    msg = _build_mime_message(
        to_addr="usuario@example.com",
        subject=email.subject,
        body_html=email.body_html,
        body_plain=email.body_plain,
    )

    assert msg.get_content_type() == "multipart/related"
    assert msg["From"].startswith(BRAND_NAME)
    assert msg["Auto-Submitted"] == "auto-generated"
    assert msg["Message-ID"].endswith("@bmsc.com.bo>")
    assert msg["X-Mailer"] == "BMSC-Base-de-Conocimiento"

    parts = list(msg.walk())
    assert any(part.get_content_type() == "multipart/alternative" for part in parts)
    assert any(part.get_content_type() == "text/plain" for part in parts)
    assert any(part.get_content_type() == "text/html" for part in parts)

    inline_logos = [
        part
        for part in parts
        if part.get_content_maintype() == "image"
        and part["Content-ID"] == f"<{LOGO_CID}>"
        and part.get_content_disposition() == "inline"
    ]
    assert len(inline_logos) == 1
