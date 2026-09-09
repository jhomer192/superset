# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""Tests for SupersetAppInitializer.check_cookie_security."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from superset import config as superset_config
from superset.initialization import SupersetAppInitializer


def _make_initializer(
    *,
    samesite: str | None = "Lax",
    secure: bool = False,
    scheme: str = "http",
    proxy_fix: bool = False,
    ws_enabled: bool = False,
    ws_samesite: str | None = None,
    ws_secure: bool = False,
    debug: bool = False,
    testing: bool = False,
) -> SupersetAppInitializer:
    init = object.__new__(SupersetAppInitializer)
    init.config = {
        "SESSION_COOKIE_SAMESITE": samesite,
        "SESSION_COOKIE_SECURE": secure,
        "ENABLE_PROXY_FIX": proxy_fix,
        "WEBSOCKET_ENABLE": ws_enabled,
        "WEBSOCKET_JWT_COOKIE_SAMESITE": ws_samesite,
        "WEBSOCKET_JWT_COOKIE_SECURE": ws_secure,
    }
    app = MagicMock()
    app.debug = debug
    app.config = {"TESTING": testing, "PREFERRED_URL_SCHEME": scheme}
    init.superset_app = app
    return init


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]


def test_samesite_none_without_secure_exits_and_names_both_keys(
    caplog: pytest.LogCaptureFixture,
) -> None:
    initializer = _make_initializer(samesite="None", secure=False)
    with (
        caplog.at_level(logging.WARNING, logger="superset.initialization"),
        patch("superset.initialization.is_test", return_value=False),
        pytest.raises(SystemExit) as exc_info,
    ):
        initializer.check_cookie_security()
    assert exc_info.value.code == 1
    assert any(
        "SESSION_COOKIE_SAMESITE" in msg and "SESSION_COOKIE_SECURE" in msg
        for msg in _warnings(caplog)
    )


def test_samesite_none_with_secure_starts_clean(
    caplog: pytest.LogCaptureFixture,
) -> None:
    initializer = _make_initializer(samesite="None", secure=True)
    with (
        caplog.at_level(logging.WARNING, logger="superset.initialization"),
        patch("superset.initialization.is_test", return_value=False),
    ):
        initializer.check_cookie_security()  # no raise
    assert _warnings(caplog) == []


def test_shipped_defaults_start_clean(caplog: pytest.LogCaptureFixture) -> None:
    initializer = _make_initializer(
        samesite=superset_config.SESSION_COOKIE_SAMESITE,
        secure=superset_config.SESSION_COOKIE_SECURE,
        scheme="http",
        proxy_fix=superset_config.ENABLE_PROXY_FIX,
    )
    with (
        caplog.at_level(logging.WARNING, logger="superset.initialization"),
        patch("superset.initialization.is_test", return_value=False),
    ):
        initializer.check_cookie_security()  # no raise
    assert _warnings(caplog) == []


@pytest.mark.parametrize(
    "scheme, proxy_fix", [("https", False), ("http", True), ("https", True)]
)
def test_https_deployment_without_secure_warns_but_starts(
    caplog: pytest.LogCaptureFixture, scheme: str, proxy_fix: bool
) -> None:
    initializer = _make_initializer(secure=False, scheme=scheme, proxy_fix=proxy_fix)
    with (
        caplog.at_level(logging.WARNING, logger="superset.initialization"),
        patch("superset.initialization.is_test", return_value=False),
    ):
        initializer.check_cookie_security()  # no raise
    assert any(
        r.levelno == logging.WARNING and "SESSION_COOKIE_SECURE" in r.getMessage()
        for r in caplog.records
    )


def test_https_deployment_with_secure_is_silent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    initializer = _make_initializer(secure=True, scheme="https", proxy_fix=True)
    with (
        caplog.at_level(logging.WARNING, logger="superset.initialization"),
        patch("superset.initialization.is_test", return_value=False),
    ):
        initializer.check_cookie_security()
    assert _warnings(caplog) == []


@pytest.mark.parametrize("debug, testing", [(True, False), (False, True)])
def test_invalid_combination_warns_but_starts_in_debug_or_testing(
    caplog: pytest.LogCaptureFixture, debug: bool, testing: bool
) -> None:
    initializer = _make_initializer(
        samesite="None", secure=False, debug=debug, testing=testing
    )
    with (
        caplog.at_level(logging.WARNING, logger="superset.initialization"),
        patch("superset.initialization.is_test", return_value=False),
    ):
        initializer.check_cookie_security()  # no raise
    assert any("SESSION_COOKIE_SAMESITE" in msg for msg in _warnings(caplog))


def test_invalid_combination_warns_but_starts_under_is_test(
    caplog: pytest.LogCaptureFixture,
) -> None:
    initializer = _make_initializer(samesite="None", secure=False)
    with (
        caplog.at_level(logging.WARNING, logger="superset.initialization"),
        patch("superset.initialization.is_test", return_value=True),
    ):
        initializer.check_cookie_security()  # no raise
    assert any("SESSION_COOKIE_SAMESITE" in msg for msg in _warnings(caplog))


def test_websocket_pair_checked_when_enabled(
    caplog: pytest.LogCaptureFixture,
) -> None:
    initializer = _make_initializer(
        ws_enabled=True, ws_samesite="None", ws_secure=False
    )
    with (
        caplog.at_level(logging.WARNING, logger="superset.initialization"),
        patch("superset.initialization.is_test", return_value=False),
        pytest.raises(SystemExit) as exc_info,
    ):
        initializer.check_cookie_security()
    assert exc_info.value.code == 1
    assert any(
        "WEBSOCKET_JWT_COOKIE_SAMESITE" in msg and "WEBSOCKET_JWT_COOKIE_SECURE" in msg
        for msg in _warnings(caplog)
    )


def test_websocket_pair_ignored_when_disabled(
    caplog: pytest.LogCaptureFixture,
) -> None:
    initializer = _make_initializer(
        ws_enabled=False, ws_samesite="None", ws_secure=False
    )
    with (
        caplog.at_level(logging.WARNING, logger="superset.initialization"),
        patch("superset.initialization.is_test", return_value=False),
    ):
        initializer.check_cookie_security()  # no raise
    assert _warnings(caplog) == []


def test_websocket_pair_with_secure_starts_clean(
    caplog: pytest.LogCaptureFixture,
) -> None:
    initializer = _make_initializer(ws_enabled=True, ws_samesite="None", ws_secure=True)
    with (
        caplog.at_level(logging.WARNING, logger="superset.initialization"),
        patch("superset.initialization.is_test", return_value=False),
    ):
        initializer.check_cookie_security()  # no raise
    assert _warnings(caplog) == []


def test_shipped_cookie_defaults_unchanged() -> None:
    assert superset_config.SESSION_COOKIE_SECURE is False
    assert superset_config.SESSION_COOKIE_SAMESITE == "Lax"
    assert superset_config.WEBSOCKET_JWT_COOKIE_SECURE is False
    assert superset_config.WEBSOCKET_JWT_COOKIE_SAMESITE is None
