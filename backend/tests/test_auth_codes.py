from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers.auth import (
    MAX_CODE_ATTEMPTS,
    PURPOSE_FIRST_LOGIN,
    PURPOSE_PASSWORD_RESET,
    _clear_verification_code,
    _set_verification_code,
    _validate_verification_code,
)


def make_user():
    return SimpleNamespace(
        verification_code=None,
        verification_code_hash=None,
        verification_code_expires_at=None,
        verification_code_attempts=0,
        verification_code_sent_at=None,
        verification_code_purpose=None,
    )


def test_set_verification_code_hashes_and_scopes_code():
    user = make_user()
    now = datetime.now(timezone.utc)

    _set_verification_code(user, "123456", PURPOSE_FIRST_LOGIN, now)

    assert user.verification_code is None
    assert user.verification_code_hash != "123456"
    assert user.verification_code_purpose == PURPOSE_FIRST_LOGIN
    assert user.verification_code_attempts == 0
    assert user.verification_code_sent_at == now
    assert user.verification_code_expires_at > now


def test_validate_verification_code_rejects_wrong_purpose():
    user = make_user()
    now = datetime.now(timezone.utc)
    _set_verification_code(user, "123456", PURPOSE_PASSWORD_RESET, now)

    with pytest.raises(HTTPException):
        _validate_verification_code(user, "123456", PURPOSE_FIRST_LOGIN, now)


def test_validate_verification_code_counts_wrong_attempts():
    user = make_user()
    now = datetime.now(timezone.utc)
    _set_verification_code(user, "123456", PURPOSE_FIRST_LOGIN, now)

    with pytest.raises(HTTPException):
        _validate_verification_code(user, "000000", PURPOSE_FIRST_LOGIN, now)

    assert user.verification_code_attempts == 1


def test_validate_verification_code_rejects_expired_code():
    user = make_user()
    now = datetime.now(timezone.utc)
    _set_verification_code(user, "123456", PURPOSE_FIRST_LOGIN, now)
    user.verification_code_expires_at = now - timedelta(seconds=1)

    with pytest.raises(HTTPException):
        _validate_verification_code(user, "123456", PURPOSE_FIRST_LOGIN, now)


def test_validate_verification_code_rejects_after_max_attempts():
    user = make_user()
    now = datetime.now(timezone.utc)
    _set_verification_code(user, "123456", PURPOSE_FIRST_LOGIN, now)
    user.verification_code_attempts = MAX_CODE_ATTEMPTS

    with pytest.raises(HTTPException):
        _validate_verification_code(user, "123456", PURPOSE_FIRST_LOGIN, now)


def test_clear_verification_code_removes_all_reset_state():
    user = make_user()
    now = datetime.now(timezone.utc)
    _set_verification_code(user, "123456", PURPOSE_FIRST_LOGIN, now)

    _clear_verification_code(user)

    assert user.verification_code is None
    assert user.verification_code_hash is None
    assert user.verification_code_expires_at is None
    assert user.verification_code_attempts == 0
    assert user.verification_code_sent_at is None
    assert user.verification_code_purpose is None
