"""pytest plugin: push a ``test_pass`` event on every green session.

Contract:

- The plugin is registered via a ``pytest11`` entry point in
  ``pyproject.toml`` so it auto-loads when ``engram-bridge`` is on the
  same Python path as pytest.
- If the bridge is disabled (no config / no api_key / enabled: false),
  every hook silently no-ops. A broken or misconfigured bridge MUST
  NOT break a test run.
- We catch ``Exception`` at every boundary because "the bridge crashed
  during pytest collection" is, by policy, never a legitimate reason
  to fail somebody's suite.

The plugin records a monotonic start time in ``pytest_sessionstart``
and, on ``pytest_sessionfinish``, pushes a ``test_pass`` event if and
only if ``exitstatus == 0``.
"""

from __future__ import annotations

import os
import time
from typing import Any


_START_ATTR = "_pytest_engram_start"


def _safe_rootdir(session: Any) -> str:
    """Best-effort ``os.path.basename(rootdir)``.

    pytest exposes ``session.config.rootpath`` (newer) or
    ``session.config.rootdir`` (older). We try both and fall back to
    the cwd if neither is available.
    """
    config = getattr(session, "config", None)
    if config is not None:
        rootpath = getattr(config, "rootpath", None)
        if rootpath is not None:
            try:
                return os.path.basename(str(rootpath))
            except Exception:  # noqa: BLE001
                pass
        rootdir = getattr(config, "rootdir", None)
        if rootdir is not None:
            try:
                return os.path.basename(str(rootdir))
            except Exception:  # noqa: BLE001
                pass
    try:
        return os.path.basename(os.getcwd())
    except OSError:
        return "pytest"


def pytest_sessionstart(session: Any) -> None:
    """Stash a monotonic start time on the config so we can compute
    duration in ``sessionfinish``. Wrapped in ``try/except`` so a
    pathological pytest fork can't crash the suite."""
    try:
        config = getattr(session, "config", None)
        if config is not None:
            setattr(config, _START_ATTR, time.monotonic())
    except Exception:  # noqa: BLE001
        pass


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    """Push a ``test_pass`` event when the suite exits cleanly.

    Exit status 0 means pytest ran every collected test and none
    failed. Any other status (1 = failures, 2 = internal error,
    5 = no tests collected, etc.) is a deliberate "don't push".
    """
    try:
        if int(exitstatus) != 0:
            return
    except (TypeError, ValueError):
        return

    try:
        start = getattr(
            getattr(session, "config", None), _START_ATTR, None
        )
        if start is None:
            duration = 0.0
        else:
            duration = max(0.0, time.monotonic() - float(start))
    except Exception:  # noqa: BLE001
        duration = 0.0

    try:
        test_count = int(getattr(session, "testscollected", 0) or 0)
    except (TypeError, ValueError):
        test_count = 0

    # Guard the bridge import so a broken bridge install can't ever
    # crash a pytest run. Everything below is best-effort.
    try:
        from .push import push_test_pass  # type: ignore
    except Exception:  # noqa: BLE001
        return

    try:
        push_test_pass(
            suite_name=_safe_rootdir(session),
            duration=duration,
            test_count=test_count,
            runner="pytest",
        )
    except Exception:  # noqa: BLE001
        # Anything — network, auth, logging, import-time crash — is
        # swallowed. The bridge is off-by-default and always silent
        # on failure. This is the hard rule.
        return
