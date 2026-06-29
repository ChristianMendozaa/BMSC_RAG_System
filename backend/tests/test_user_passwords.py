from app.routers.users import (
    TEMPORARY_PASSWORD_ALPHABET,
    TEMPORARY_PASSWORD_DIGITS,
    TEMPORARY_PASSWORD_LENGTH,
    TEMPORARY_PASSWORD_LETTERS,
    TEMPORARY_PASSWORD_SYMBOLS,
    _generate_temporary_password,
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
