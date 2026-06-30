from fastapi import HTTPException

from app.routers.collections import _normalize_collection_name


def test_normalize_collection_name_strips_whitespace():
    assert _normalize_collection_name("  Normativa interna  ") == "Normativa interna"


def test_normalize_collection_name_rejects_blank():
    try:
        _normalize_collection_name("   ")
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "nombre" in exc.detail
    else:
        raise AssertionError("Expected HTTPException")
