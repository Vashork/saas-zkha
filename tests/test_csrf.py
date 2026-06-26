"""
Tests for CSRF module functions.
"""

import pytest

from app.csrf import (
    _make_token,
    _constant_time_compare,
    _EXEMPT_PATHS,
    CSRF_COOKIE,
    CSRF_FIELD,
    CSRF_HEADER,
)


# --- _EXEMPT_PATHS ---

def test_exempt_paths_contains_login():
    assert "/login" in _EXEMPT_PATHS


def test_exempt_paths_contains_logout():
    assert "/logout" in _EXEMPT_PATHS


def test_exempt_paths_contains_health():
    assert "/health" in _EXEMPT_PATHS


def test_exempt_paths_does_not_contain_dashboard():
    assert "/dashboard" not in _EXEMPT_PATHS


# --- _make_token ---

def test_make_token_returns_string():
    token = _make_token()
    assert isinstance(token, str)


def test_make_token_length():
    token = _make_token()
    # token_hex(32) = 64 hex chars
    assert len(token) == 64


def test_make_token_unique():
    t1 = _make_token()
    t2 = _make_token()
    assert t1 != t2


def test_make_token_hex_only():
    token = _make_token()
    assert all(c in "0123456789abcdef" for c in token)


# --- _constant_time_compare ---

def test_compare_equal():
    assert _constant_time_compare("abc", "abc") is True


def test_compare_different():
    assert _constant_time_compare("abc", "xyz") is False


def test_compare_empty():
    assert _constant_time_compare("", "") is True


def test_compare_one_empty():
    assert _constant_time_compare("abc", "") is False


# --- Constants ---

def test_csrf_cookie_name():
    assert CSRF_COOKIE == "_csrf"


def test_csrf_field_name():
    assert CSRF_FIELD == "_csrf"


def test_csrf_header_name():
    assert CSRF_HEADER == "X-CSRF-Token"
