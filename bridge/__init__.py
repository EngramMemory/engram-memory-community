"""Engram Bridge — client daemon that pulls relevant memories from the
Engram cloud API and injects them as context at agent session start.

Wave 1 scope: read path only (pull, status, install).

The bridge is OFF by default. It only activates when
`~/.engram/config.yaml` exists, is enabled, and contains a valid
`api_key` beginning with `eng_live_`. In every other case, all commands
exit 0 silently so a disabled bridge never breaks a user's workflow.
"""

from __future__ import annotations

__version__ = "0.1.0"
__all__ = ["__version__"]
