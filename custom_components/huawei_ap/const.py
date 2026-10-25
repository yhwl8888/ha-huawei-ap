"""Constants for the Huawei Access Point integration.

Transport
---------
The AP is driven over SSH (Huawei VRP CLI), not the Web UI. The Web NMS was
the original plan, but real-device testing showed two blockers:

  * the device allows only a single Web session (`ErrorMsg=1012` as soon as a
    second login happens), which makes HTTP polling fragile for an always-on
    integration;
  * `/config.cgi` rejected the session cookie handed out by `/login.cgi`,
    answering HTTP 450 "Return Login Page".

SSH (port 22, banner ``SSH-2.0-HUAWEI-1.5``) has none of those limits and
returns clean, complete CLI output.

Verified on: **Huawei AirEngine5761-11W**, VRP 5.170
(V200R023C00SPC100), FAT / Leader-AP mode, managing 2 x AP4050DE-B-S.

Note: the device requires a PTY for command execution - a bare SSH exec
channel returns an empty body. All commands therefore run inside an
allocated ``vt100`` terminal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

DOMAIN = "huawei_ap"
MANUFACTURER = "Huawei"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_PORT = "port"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_ENABLE_ALERTS = "enable_alerts"

DEFAULT_PORT = 22
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_ENABLE_ALERTS = True

MIN_SCAN_INTERVAL = 15
MAX_SCAN_INTERVAL = 600

DEFAULT_UPDATE_INTERVAL = timedelta(seconds=DEFAULT_SCAN_INTERVAL)

# Some VRP releases only offer legacy algorithms. The "+" prefix keeps the
# library defaults and appends these instead of restricting the set.
SSH_KEX_ALGS = "+diffie-hellman-group14-sha1,diffie-hellman-group1-sha1"
SSH_HOST_KEY_ALGS = "+ssh-rsa,ssh-dss"

SSH_CONNECT_TIMEOUT = 20
SSH_COMMAND_TIMEOUT = 25

# ---------------------------------------------------------------------------
# CLI commands - every command below was executed successfully on the test
# device. The first entry is used, the rest are fallbacks for other releases.
# ---------------------------------------------------------------------------
CLI_CANDIDATES: dict[str, tuple[str, ...]] = {
    "version": ("display version",),
    "cpu": ("display cpu-usage", "display cpu"),
    "memory": ("display memory-usage", "display memory"),
    "temperature": ("display temperature all", "display temperature"),
    "clients": ("display station all",),
    "aps": ("display ap all",),
    "radios": ("display radio all", "display wlan radio"),
    "interfaces": ("display interface brief",),
    "ap_stats": ("display ap statistics",),
}

# Keeps the CLI from paging with "---- More ----".
SCREEN_LENGTH_CMD = "screen-length 0 temporary"

# ---------------------------------------------------------------------------
# Platforms
# ---------------------------------------------------------------------------
PLATFORMS: list[str] = [
    "sensor",
    "binary_sensor",
    "device_tracker",
    "button",
]


@dataclass(slots=True)
class HuaweiApClientData:
    """Normalised device snapshot produced on every poll."""

    # --- identity -------------------------------------------------------
    model: str | None = None
    firmware: str | None = None
    hostname: str | None = None
    serial: str | None = None
    mac: str | None = None
    ip_address: str | None = None
    work_mode: str | None = None

    # --- health ---------------------------------------------------------
    cpu_percent: float | None = None
    cpu_max_percent: float | None = None
    memory_percent: float | None = None
    memory_total_kb: int | None = None
    memory_used_kb: int | None = None
    temperature: float | None = None
    temperature_max: float | None = None
    uptime_seconds: int | None = None

    # --- wireless -------------------------------------------------------
    client_count: int | None = None
    client_count_24g: int | None = None
    client_count_5g: int | None = None
    client_count_6g: int | None = None
    clients: list[dict] = field(default_factory=list)

    ap_count: int | None = None
    aps: list[dict] = field(default_factory=list)
    radios: list[dict] = field(default_factory=list)

    # --- alerts ---------------------------------------------------------
    power_insufficient: bool | None = None
    temperature_alarm: bool | None = None

    # --- wired ----------------------------------------------------------
    interfaces: list[dict] = field(default_factory=list)

    # --- diagnostics ----------------------------------------------------
    raw: dict = field(default_factory=dict)
    capabilities: dict = field(default_factory=dict)
