from fastapi import HTTPException

from app.routers.users import (
    BMSC_EMAIL_DOMAIN,
    TEMPORARY_PASSWORD_ALPHABET,
    TEMPORARY_PASSWORD_DIGITS,
    TEMPORARY_PASSWORD_LENGTH,
    TEMPORARY_PASSWORD_LETTERS,
    TEMPORARY_PASSWORD_SYMBOLS,
    _generate_temporary_password,
    _normalize_user_email,
    _resolve_temporary_password,
)


def test_generate_temporary_password_has_expected_shape():
    password = _generate_temporary_password()

    assert len(password) == TEMPORARY_PASSWORD_LENGTH
    assert set(password).issubset(set(TEMPORARY_PASSWORD_ALPHABET))
    assert any(char in TEMPORARY_PASSWORD_LETTERS for char in password)
    assert any(char in TEMPORARY_PASSWORD_DIGITS for char in password)
    assert any(char in TEMPORARY_PASSWORD_SYMBOLS for char in password)


def test_generate_temporary_password_varies_between_calls():
    passwords = {_generate_temporary_password() for _ in range(5)}

    assert len(passwords) > 1


def test_resolve_temporary_password_keeps_explicit_password():
    assert _resolve_temporary_password("Temporal1234") == "Temporal1234"


def test_resolve_temporary_password_generates_for_blank_values():
    for value in (None, "", "   "):
        password = _resolve_temporary_password(value)

        assert len(password) == TEMPORARY_PASSWORD_LENGTH
        assert set(password).issubset(set(TEMPORARY_PASSWORD_ALPHABET))


def test_normalize_user_email_accepts_bmsc_domain():
    assert _normalize_user_email(" Usuario.Prueba@BMSC.COM.BO ") == "usuario.prueba@bmsc.com.bo"


def test_normalize_user_email_rejects_external_domain_when_required():
    try:
        _normalize_user_email("usuario@example.com")
    except HTTPException as exc:
        assert exc.status_code == 400
        assert BMSC_EMAIL_DOMAIN in exc.detail
    else:
        raise AssertionError("Expected HTTPException")


def test_normalize_user_email_allows_external_domain_when_disabled(monkeypatch):
    from app.routers import users

    monkeypatch.setattr(users.settings, "require_bmsc_email_domain", False)

    assert _normalize_user_email("usuario@example.com") == "usuario@example.com"
