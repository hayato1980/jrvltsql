"""Exposure contract for the background updater service and the PostgreSQL launchers.

Two invariants are pinned here:

1. The trigger API is reachable from the local host only, carries no CORS grant,
   and never starts a JV-Link fetch from a GET.  The API has no authentication,
   so a wildcard bind or an ``Access-Control-Allow-Origin: *`` turns any page the
   operator opens into a remote control for the collection host.
2. A PostgreSQL password never reaches a process command line.  ``daily_sync.bat``
   already routes it through ``PGPASSWORD``; the quickstart launchers must not
   diverge from that rule.

These tests are platform independent on purpose: the behaviour they guard is not
Windows specific, and the Windows CI job runs only ``test_windows_launchers.py``.
"""

import argparse
import inspect
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.background_updater import (
    DEFAULT_API_BIND_HOST,
    DEFAULT_API_PORT,
    DEFAULT_HISTORICAL_INTERVAL_MINUTES,
    BackgroundUpdater,
    TriggerAPIHandler,
    TriggerAPIServer,
    build_forward_args,
    build_parser,
)
from scripts.quickstart import AUTO_START_SERVICE_ARGS

ROOT = Path(__file__).resolve().parents[1]
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}

PG_LAUNCHERS = (
    "quickstart_postgres_timeseries.bat",
    "quickstart_timeseries.bat",
    "daily_sync.bat",
)


def _handler(path: str) -> TriggerAPIHandler:
    """Build a handler without the BaseHTTPRequestHandler socket setup.

    Bypassing ``__init__`` keeps the routing contract testable without a live
    connection, the same technique ``test_jvlink_transport_contract.py`` uses.
    """
    handler = TriggerAPIHandler.__new__(TriggerAPIHandler)
    handler.path = path
    handler.updater = None
    handler.rate_limiter = None
    handler.status_codes = []
    handler.sent_headers = []
    handler.send_response = lambda code, *args: handler.status_codes.append(code)
    handler.send_header = lambda key, value: handler.sent_headers.append((key, value))
    handler.end_headers = lambda: None
    handler.wfile = MagicMock()
    return handler


# --------------------------------------------------------------------------
# 1. Trigger API exposure
# --------------------------------------------------------------------------

def test_api_server_binds_loopback_by_default():
    assert DEFAULT_API_BIND_HOST in LOOPBACK_HOSTS
    assert inspect.signature(TriggerAPIServer.__init__).parameters[
        "bind_host"
    ].default in LOOPBACK_HOSTS


def test_updater_passes_loopback_bind_by_default():
    assert inspect.signature(BackgroundUpdater.__init__).parameters[
        "api_bind_host"
    ].default in LOOPBACK_HOSTS


def test_started_server_listens_on_the_configured_host_only():
    server = TriggerAPIServer(MagicMock(), port=0, enable_rate_limit=False)
    assert server.start(), "API server failed to start on an ephemeral port"
    try:
        assert server.server.server_address[0] in LOOPBACK_HOSTS
    finally:
        server.stop()


def test_responses_carry_no_cors_grant():
    handler = _handler("/")
    handler._send_json_response(200, {"ok": True})

    header_names = {name.lower() for name, _ in handler.sent_headers}
    assert not any(name.startswith("access-control-") for name in header_names)


def test_options_carries_no_cors_grant():
    handler = _handler("/")
    handler.do_OPTIONS()

    header_names = {name.lower() for name, _ in handler.sent_headers}
    assert not any(name.startswith("access-control-") for name in header_names)


@pytest.mark.parametrize("path", sorted(TriggerAPIHandler.TRIGGER_ROUTES))
def test_get_never_starts_a_fetch(path):
    """GET must stay safe: a page the operator opens must not start a fetch."""
    handler = _handler(path)
    started = []
    handler._handle_trigger = lambda mode: started.append(mode)

    handler.do_GET()

    assert started == []
    assert handler.status_codes == [405]


@pytest.mark.parametrize(
    "path,mode", sorted(TriggerAPIHandler.TRIGGER_ROUTES.items())
)
def test_post_starts_the_requested_fetch(path, mode):
    handler = _handler(path)
    started = []
    handler._handle_trigger = lambda requested: started.append(requested)

    handler.do_POST()

    assert started == [mode]


def test_status_stays_readable_over_get():
    handler = _handler("/status")
    read = []
    handler._handle_status = lambda: read.append(True)

    handler.do_GET()

    assert read == [True]


# --------------------------------------------------------------------------
# 2. Argument forwarding (a non-default value must survive --background)
# --------------------------------------------------------------------------

def test_parser_defaults_match_the_module_constants():
    defaults = build_parser().parse_args([])

    assert defaults.api_bind == DEFAULT_API_BIND_HOST
    assert defaults.api_port == DEFAULT_API_PORT
    assert defaults.interval == DEFAULT_HISTORICAL_INTERVAL_MINUTES


def test_defaults_are_not_forwarded():
    assert build_forward_args(build_parser().parse_args([])) == []


@pytest.mark.parametrize(
    "argv,expected",
    [
        (["--interval", "30"], ["--interval", "30"]),
        (["--interval", "15"], ["--interval", "15"]),
        (["--api-port", "9000"], ["--api-port", "9000"]),
        (["--api-bind", "0.0.0.0"], ["--api-bind", "0.0.0.0"]),
        (["--no-api"], ["--no-api"]),
    ],
)
def test_explicit_values_are_forwarded_to_the_background_process(argv, expected):
    """A value the operator typed must reach the detached process.

    ``--interval 30`` in particular used to be compared against a literal 30
    while the parser default was 60, so the daemon silently ran hourly.
    """
    assert build_forward_args(build_parser().parse_args(argv)) == expected


# --------------------------------------------------------------------------
# 3. Auto-start writes explicit arguments
# --------------------------------------------------------------------------

def test_auto_start_args_are_explicit_and_match_the_service_defaults():
    args = argparse.Namespace(**vars(build_parser().parse_args(
        list(AUTO_START_SERVICE_ARGS)
    )))

    assert args.api_bind == DEFAULT_API_BIND_HOST
    assert args.api_port == DEFAULT_API_PORT
    assert args.interval == DEFAULT_HISTORICAL_INTERVAL_MINUTES
    # The bind must be named rather than inherited, so a future change to the
    # module default cannot silently widen an existing auto-start entry.
    assert "--api-bind" in AUTO_START_SERVICE_ARGS


# --------------------------------------------------------------------------
# 4. PostgreSQL password never reaches a command line
# --------------------------------------------------------------------------

@pytest.mark.parametrize("launcher", PG_LAUNCHERS)
def test_launchers_never_pass_the_password_on_the_command_line(launcher):
    text = (ROOT / launcher).read_text(encoding="utf-8")
    assert "--pg-password" not in text


@pytest.mark.parametrize("launcher", PG_LAUNCHERS)
def test_launchers_hand_the_password_over_through_pgpassword(launcher):
    text = (ROOT / launcher).read_text(encoding="utf-8")
    assert 'set "PGPASSWORD=%POSTGRES_PASSWORD%"' in text
    assert "if not defined POSTGRES_PASSWORD" in text


def test_quickstart_no_longer_advertises_a_default_password():
    text = (ROOT / "scripts" / "quickstart.py").read_text(encoding="utf-8")
    assert "settings['pg_password'] = 'postgres'" not in text
