#!/usr/bin/env python3
"""Docker smoke QA helper for the hardened runtime model.

This script intentionally uses only quiet Compose validation (`config -q`) and never
prints the resolved Compose config because it may contain secrets from `.env`.

It performs non-destructive checks that are safe for a local release smoke:

- validate Compose syntax quietly;
- optionally build the web and bot images sequentially with a retry;
- optionally start the stack without forcing a second parallel rebuild;
- wait for `/health` through nginx;
- verify `/uploads/...` is not publicly served;
- verify `/login` reaches the web app;
- show bounded service status/log tails for evidence.

Authenticated business checks such as backup page and receipt upload/download still
require real credentials and should be captured manually, or added later through a
separate authenticated smoke flow.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "http://localhost"
SMOKE_SERVICES = ("web", "bot")


@dataclass(frozen=True)
class CommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str


def _run(args: Iterable[str], *, check: bool = True, capture: bool = True) -> CommandResult:
    argv = list(args)
    print(f"$ {' '.join(argv)}")
    completed = subprocess.run(
        argv,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=False,
    )
    result = CommandResult(
        args=argv,
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )
    if check and result.returncode != 0:
        if result.stdout.strip():
            print(result.stdout.rstrip())
        if result.stderr.strip():
            print(result.stderr.rstrip(), file=sys.stderr)
        raise SystemExit(result.returncode)
    return result


def _run_with_retry(args: Iterable[str], *, attempts: int, capture: bool = True) -> CommandResult:
    last: CommandResult | None = None
    for attempt in range(1, attempts + 1):
        result = _run(args, check=False, capture=capture)
        if result.returncode == 0:
            return result
        last = result
        if attempt < attempts:
            print(f"command failed with exit code {result.returncode}; retrying once after 5s")
            time.sleep(5)
    assert last is not None
    if last.stdout.strip():
        print(last.stdout.rstrip())
    if last.stderr.strip():
        print(last.stderr.rstrip(), file=sys.stderr)
    raise SystemExit(last.returncode)


def _detect_compose() -> list[str]:
    """Prefer Docker Compose plugin, fall back to docker-compose v1."""
    plugin = _run(["docker", "compose", "version"], check=False)
    if plugin.returncode == 0:
        return ["docker", "compose"]
    legacy = _run(["docker-compose", "version"], check=False)
    if legacy.returncode == 0:
        return ["docker-compose"]
    raise SystemExit("Docker Compose plugin/v1 was not found")


def _build_images_sequentially(compose: list[str], *, attempts: int) -> None:
    for service in SMOKE_SERVICES:
        _run_with_retry([*compose, "build", "--no-cache", service], attempts=attempts, capture=False)


def _http_get(url: str, *, timeout: float = 5.0) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "zhkh-docker-smoke/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read(4096).decode("utf-8", errors="replace")
            return response.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read(4096).decode("utf-8", errors="replace")
        return exc.code, body


def _wait_for_health(base_url: str, *, timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    health_url = f"{base_url.rstrip('/')}/health"
    last_error = "not checked"
    while time.monotonic() < deadline:
        try:
            status, body = _http_get(health_url, timeout=5)
            if status == 200:
                payload = json.loads(body)
                if payload.get("status") == "ok" and payload.get("database") == "ok":
                    print(f"health ok: {body.strip()}")
                    return
                last_error = f"unexpected health payload: {body.strip()}"
            else:
                last_error = f"HTTP {status}: {body[:200]}"
        except Exception as exc:  # pragma: no cover - depends on local Docker state
            last_error = str(exc)
        time.sleep(2)
    raise SystemExit(f"health check did not become ready within {timeout_seconds}s: {last_error}")


def _assert_uploads_not_public(base_url: str) -> None:
    status, _ = _http_get(f"{base_url.rstrip('/')}/uploads/docker-smoke-missing.txt", timeout=5)
    if status in {401, 403, 404}:
        print(f"/uploads public access blocked as expected: HTTP {status}")
        return
    raise SystemExit(f"/uploads returned unexpected HTTP {status}; receipts must not be public")


def _assert_login_reachable(base_url: str) -> None:
    status, body = _http_get(f"{base_url.rstrip('/')}/login", timeout=5)
    if status == 200 and ("login" in body.lower() or "csrf" in body.lower() or "пароль" in body.lower()):
        print("/login reachable")
        return
    raise SystemExit(f"/login returned unexpected response: HTTP {status}")


def _print_bounded_logs(compose: list[str], service: str) -> None:
    result = _run([*compose, "logs", "--tail=120", service], check=False)
    output = (result.stdout + result.stderr).strip()
    print(f"--- {service} logs tail ---")
    print(output or "<empty>")
    lowered = output.lower()
    blocked_terms = ("permission denied", "traceback", "startup failed")
    found = [term for term in blocked_terms if term in lowered]
    if found:
        raise SystemExit(f"{service} logs contain smoke-blocking terms: {', '.join(found)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local Docker smoke QA for ZhKH Bot.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Base URL exposed by nginx, default: http://localhost")
    parser.add_argument("--health-timeout", type=int, default=90, help="Seconds to wait for /health")
    parser.add_argument("--build-attempts", type=int, default=2, help="Attempts for each image build, default: 2")
    parser.add_argument("--skip-build", action="store_true", help="Skip sequential image builds")
    parser.add_argument("--skip-up", action="store_true", help="Skip docker compose up -d")
    parser.add_argument("--skip-logs", action="store_true", help="Skip bounded service log evidence")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    compose = _detect_compose()
    print(f"Using Compose command: {' '.join(compose)}")

    # Do not replace this with plain `config`: full config may print secrets from .env.
    _run([*compose, "config", "-q"])

    if not args.skip_build:
        _build_images_sequentially(compose, attempts=args.build_attempts)
    if not args.skip_up:
        # Build is done above sequentially to avoid flaky parallel resolver/index failures.
        _run([*compose, "up", "-d"], capture=False)

    _run([*compose, "ps"], check=False)
    _wait_for_health(args.base_url, timeout_seconds=args.health_timeout)
    _assert_login_reachable(args.base_url)
    _assert_uploads_not_public(args.base_url)

    if not args.skip_logs:
        for service in ("web", "nginx", "bot"):
            _print_bounded_logs(compose, service)

    print("SUCCESS: Docker smoke QA baseline passed.")
    print("Manual evidence still required for authenticated backup page and receipt upload/download.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
