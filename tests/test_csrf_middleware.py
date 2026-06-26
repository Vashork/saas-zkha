"""Regression tests for CSRF middleware request handling."""

import pytest
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from app.csrf import CSRF_COOKIE, CSRF_FIELD, CSRF_HEADER, CsrfMiddleware


TOKEN = "expected-form-token"


def make_request(
    path: str,
    body: bytes,
    content_type: str,
    *,
    cookie_token: str | None = TOKEN,
    header_token: str | None = None,
) -> Request:
    headers = [(b"content-type", content_type.encode("ascii"))]
    if cookie_token is not None:
        headers.append((b"cookie", f"{CSRF_COOKIE}={cookie_token}".encode("ascii")))
    if header_token is not None:
        headers.append((CSRF_HEADER.lower().encode("ascii"), header_token.encode("ascii")))

    delivered = False

    async def receive():
        nonlocal delivered
        if delivered:
            return {"type": "http.request", "body": b"", "more_body": False}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": headers,
            "query_string": b"",
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "scheme": "http",
        },
        receive=receive,
    )


async def dispatch(request: Request):
    middleware = CsrfMiddleware(app=lambda scope, receive, send: None)
    called = False

    async def call_next(inner_request):
        nonlocal called
        called = True
        await inner_request.body()
        return Response("ok", status_code=200)

    response = await middleware.dispatch(request, call_next)
    return response, called


def multipart_body(field_value: str | None):
    boundary = "----zhkh-test-boundary"
    parts = []
    if field_value is not None:
        parts.append(
            f"--{boundary}\r\n"
            f"Content-Disposition: form-data; name=\"{CSRF_FIELD}\"\r\n\r\n"
            f"{field_value}\r\n"
        )
    parts.append(
        f"--{boundary}\r\n"
        "Content-Disposition: form-data; name=\"name\"\r\n\r\n"
        "value\r\n"
    )
    parts.append(f"--{boundary}--\r\n")
    return "".join(parts).encode("utf-8"), f"multipart/form-data; boundary={boundary}"


def assert_blocked(response, called):
    assert isinstance(response, RedirectResponse)
    assert response.status_code == 403
    assert response.headers["location"] == "/?csrf=1"
    assert called is False


@pytest.mark.asyncio
async def test_urlencoded_form_with_hidden_field_succeeds():
    request = make_request(
        "/settings/save",
        f"{CSRF_FIELD}={TOKEN}&theme=dark".encode("utf-8"),
        "application/x-www-form-urlencoded",
    )

    response, called = await dispatch(request)

    assert response.status_code == 200
    assert called is True


@pytest.mark.asyncio
async def test_urlencoded_form_without_hidden_field_fails():
    request = make_request(
        "/settings/save",
        b"theme=dark",
        "application/x-www-form-urlencoded",
    )

    response, called = await dispatch(request)

    assert_blocked(response, called)


@pytest.mark.asyncio
async def test_urlencoded_form_with_mismatched_hidden_field_fails():
    request = make_request(
        "/settings/save",
        f"{CSRF_FIELD}=other-value&theme=dark".encode("utf-8"),
        "application/x-www-form-urlencoded",
    )

    response, called = await dispatch(request)

    assert_blocked(response, called)


@pytest.mark.asyncio
async def test_multipart_form_with_hidden_field_succeeds():
    body, content_type = multipart_body(TOKEN)
    request = make_request("/payments/add", body, content_type)

    response, called = await dispatch(request)

    assert response.status_code == 200
    assert called is True


@pytest.mark.asyncio
async def test_multipart_form_without_hidden_field_fails():
    body, content_type = multipart_body(None)
    request = make_request("/payments/add", body, content_type)

    response, called = await dispatch(request)

    assert_blocked(response, called)


@pytest.mark.asyncio
async def test_multipart_form_with_mismatched_hidden_field_fails():
    body, content_type = multipart_body("other-value")
    request = make_request("/payments/add", body, content_type)

    response, called = await dispatch(request)

    assert_blocked(response, called)


@pytest.mark.asyncio
async def test_ajax_theme_save_with_header_succeeds():
    request = make_request(
        "/settings/theme",
        b'{"theme":"light"}',
        "application/json",
        header_token=TOKEN,
    )

    response, called = await dispatch(request)

    assert response.status_code == 200
    assert called is True


@pytest.mark.asyncio
async def test_ajax_theme_save_without_header_fails():
    request = make_request(
        "/settings/theme",
        b'{"theme":"light"}',
        "application/json",
    )

    response, called = await dispatch(request)

    assert_blocked(response, called)


@pytest.mark.asyncio
async def test_ajax_theme_save_with_mismatched_header_fails():
    request = make_request(
        "/settings/theme",
        b'{"theme":"light"}',
        "application/json",
        header_token="other-value",
    )

    response, called = await dispatch(request)

    assert_blocked(response, called)
