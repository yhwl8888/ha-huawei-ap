"""Parsers for Huawei AirEngine CLI output.

Every pattern below was written against real output captured from an
AirEngine5761-11W (VRP 5.170 / V200R023C00SPC100, FAT Leader-AP mode):

``display version``
    VRP (R) software, Version 5.170 (AirEngine 5700 V200R023C00SPC100)
    Huawei AirEngine5761-11W Router uptime is 14 weeks, 5 days, 7 hours, 26 minutes
    3. Board    Type     : AirEngine5761-11W

``display cpu-usage``
    CPU   Usage: 13.2%   Max: 76.9%

``display memory-usage``
    System Total Memory Is: 574716 kbytes
    Memory Using Percentage Is: 34%

``display temperature all``
    0   -   1   AirEngine5761-11W-CPU0   NORMAL   105   -5   58

``display station all``
    ddee-ff00-5566   2   aabb-cc00-3344   0/3   2.4G   11n   72/72   -43   1   192.168.1.166   office-wifi
    Total: 18 2.4G: 12 5G: 6 6G: 0

``display ap all``
    0*   aabb-cc00-1122   aabb-cc00-1122   default   default   192.168.1.50   AirEngine5761-11W   nor   8   103D:7H:26M:48S   P

``display radio all``
    0   aabb-cc00-1122   0   2.4G   11ax   on   5/20M   24/24   5   19%   normal
"""

from __future__ import annotations

import logging
import re

from .const import HuaweiApClientData

_LOGGER = logging.getLogger(__name__)

_HUAWEI_MAC_RE = re.compile(r"^[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}$")

_UNIT_SECONDS = {
    "year": 31536000,
    "week": 604800,
    "day": 86400,
    "hour": 3600,
    "minute": 60,
    "second": 1,
}


def format_mac(raw: str | None) -> str | None:
    """``aabb-cc00-1122`` -> ``AA:BB:CC:00:11:22``."""
    if not raw or not _HUAWEI_MAC_RE.match(raw):
        return raw
    digits = raw.replace("-", "").upper()
    return ":".join(digits[i : i + 2] for i in range(0, 12, 2))


def parse_vrp_duration(text: str) -> int | None:
    """Parse VRP durations like ``103D:7H:26M:48S`` or ``2Y:3W:4D:5H:6M:7S``."""
    match = re.search(
        r"(?:(\d+)Y:)?(?:(\d+)W:)?(?:(\d+)D:)?(?:(\d+)H:)?(?:(\d+)M:)?(\d+)S",
        text,
    )
    if not match:
        return None
    years, weeks, days, hours, minutes, seconds = (
        int(g) if g else 0 for g in match.groups()
    )
    return (
        years * _UNIT_SECONDS["year"]
        + weeks * _UNIT_SECONDS["week"]
        + days * _UNIT_SECONDS["day"]
        + hours * _UNIT_SECONDS["hour"]
        + minutes * _UNIT_SECONDS["minute"]
        + seconds
    )


def parse_prose_duration(text: str) -> int | None:
    """Parse ``14 weeks, 5 days, 7 hours, 26 minutes``."""
    total = 0
    found = False
    for value, unit in re.findall(r"(\d+)\s*([A-Za-z]+)", text):
        key = unit.lower().rstrip("s")
        if key in _UNIT_SECONDS:
            total += int(value) * _UNIT_SECONDS[key]
            found = True
    return total if found else None


# ---------------------------------------------------------------------------
# display version
# ---------------------------------------------------------------------------
def parse_version(text: str) -> dict:
    result: dict = {
        "model": None,
        "firmware": None,
        "firmware_full": None,
        "uptime_seconds": None,
        "work_mode": None,
        "serial": None,
        "sdram_mb": None,
    }
    if not text:
        return result

    match = re.search(r"Version\s+([\d.]+)\s*\(", text)
    if match:
        result["firmware"] = match.group(1)

    match = re.search(r"Version\s+[\d.]+\s*\(([^)]+)\)", text)
    if match:
        result["firmware_full"] = match.group(1).strip()

    # "3. Board    Type     : AirEngine5761-11W" is the authoritative model.
    match = re.search(r"Board\s+Type\s*:\s*(\S+)", text)
    if match:
        result["model"] = match.group(1)
    else:
        match = re.search(r"^Huawei\s+(\S+)\s+Router\s+uptime", text, re.MULTILINE)
        if match:
            result["model"] = match.group(1)

    match = re.search(r"uptime is\s+([^\r\n]+)", text)
    if match:
        result["uptime_seconds"] = parse_prose_duration(match.group(1))

    match = re.search(r"Current Work Mode\s*:\s*(\S+)", text)
    if match:
        result["work_mode"] = match.group(1)

    match = re.search(r"SDRAM Memory Size\s*:\s*(\d+)", text)
    if match:
        result["sdram_mb"] = int(match.group(1))

    match = re.search(r"(?:SN|Serial\s+Number)\s*[:=]\s*(\S+)", text)
    if match:
        result["serial"] = match.group(1)
    return result


# ---------------------------------------------------------------------------
# display cpu-usage / memory-usage
# ---------------------------------------------------------------------------
def parse_cpu(text: str) -> tuple[float | None, float | None]:
    """Return (current, peak) CPU percentage."""
    if not text:
        return None, None
    current = peak = None
    match = re.search(r"CPU\s+Usage\s*:\s*([\d.]+)\s*%", text)
    if match:
        current = float(match.group(1))
    match = re.search(r"Max\s*:\s*([\d.]+)\s*%", text)
    if match:
        peak = float(match.group(1))
    if current is None:
        match = re.search(r"CPU\s+utilization[^:]*:\s*([\d.]+)\s*%", text)
        if match:
            current = float(match.group(1))
    return current, peak


def parse_memory(text: str) -> tuple[float | None, int | None, int | None]:
    """Return (percent, total_kb, used_kb)."""
    if not text:
        return None, None, None
    percent = total = used = None
    match = re.search(r"Memory Using Percentage Is\s*:\s*(\d+)\s*%", text)
    if match:
        percent = float(match.group(1))
    match = re.search(r"System Total Memory Is\s*:\s*(\d+)", text)
    if match:
        total = int(match.group(1))
    match = re.search(r"Total Memory Used Is\s*:\s*(\d+)", text)
    if match:
        used = int(match.group(1))
    if percent is None and total and used:
        percent = round(used / total * 100, 1)
    return percent, total, used


# ---------------------------------------------------------------------------
# display temperature all
# ---------------------------------------------------------------------------
def parse_temperature(text: str) -> tuple[float | None, float | None, bool]:
    """Return (max_temp, average_temp, any_alarm).

    Row layout: slot  card  sensor_no  sensor_name  status  upper  lower  temp
    """
    if not text:
        return None, None, False

    temps: list[float] = []
    alarm = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("-"):
            continue
        match = re.search(
            r"(NORMAL|ABNORMAL|MINOR|MAJOR|CRITICAL)\s+"
            r"(-?\d+)\s+(-?\d+)\s+(-?\d+(?:\.\d+)?)",
            stripped,
            re.IGNORECASE,
        )
        if not match:
            continue
        status, _upper, _lower, temp = match.groups()
        temps.append(float(temp))
        if status.upper() != "NORMAL":
            alarm = True

    if not temps:
        single = re.search(r"Current temperature\s*:\s*(-?\d+)", text)
        if single:
            value = float(single.group(1))
            return value, value, False
        return None, None, False

    return max(temps), round(sum(temps) / len(temps), 1), alarm


# ---------------------------------------------------------------------------
# display station all
# ---------------------------------------------------------------------------
_STATION_RE = re.compile(
    r"^(?P<mac>[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4})\s+"
    r"(?P<ap_id>\d+)\s+"
    r"(?P<ap_name>\S+)\s+"
    r"(?P<rf>\d+/\d+)\s+"
    r"(?P<band>\S+)\s+"
    r"(?P<type>\S+)\s+"
    r"(?P<rate>\d+/\d+)\s+"
    r"(?P<rssi>-?\d+)\s+"
    r"(?P<vlan>\d+)\s+"
    r"(?P<ip>\S+)\s+"
    r"(?P<ssid>\S+)"
)

_STATION_TOTAL_RE = re.compile(
    r"Total:\s*(\d+)\s+2\.4G:\s*(\d+)\s+5G:\s*(\d+)\s+6G:\s*(\d+)"
)


def parse_stations(text: str) -> tuple[dict, list[dict]]:
    """Return (counts, client_list)."""
    counts = {"total": None, "2.4G": None, "5G": None, "6G": None}
    clients: list[dict] = []
    if not text:
        return counts, clients

    for line in text.splitlines():
        match = _STATION_RE.match(line.strip())
        if not match:
            continue
        row = match.groupdict()
        rx, _, tx = row["rate"].partition("/")
        clients.append(
            {
                "mac": format_mac(row["mac"]),
                "ap_id": int(row["ap_id"]),
                "ap_name": row["ap_name"],
                "radio": row["rf"],
                "band": row["band"],
                "phy": row["type"],
                "rx_mbps": _safe_int(rx),
                "tx_mbps": _safe_int(tx),
                "rssi": _safe_int(row["rssi"]),
                "vlan": _safe_int(row["vlan"]),
                "ip": row["ip"],
                "ssid": row["ssid"],
            }
        )

    match = _STATION_TOTAL_RE.search(text)
    if match:
        counts["total"] = int(match.group(1))
        counts["2.4G"] = int(match.group(2))
        counts["5G"] = int(match.group(3))
        counts["6G"] = int(match.group(4))
    elif clients:
        counts["total"] = len(clients)
    return counts, clients


# ---------------------------------------------------------------------------
# display ap all
# ---------------------------------------------------------------------------
_AP_ROW_RE = re.compile(
    r"^(?P<id>\d+)(?P<leader>\*)?\s+"
    r"(?P<mac>[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4})\s+"
    r"(?P<name>\S+)\s+"
    r"(?P<group>\S+)\s+"
    r"(?P<zone>\S+)\s+"
    r"(?P<ip>\d+\.\d+\.\d+\.\d+)\s+"
    r"(?P<type>\S+)\s+"
    r"(?P<state>\S+)\s+"
    r"(?P<sta>\d+)\s+"
    r"(?P<uptime>\S+)"
)


def parse_aps(text: str) -> tuple[int | None, list[dict], bool]:
    """Return (ap_count, ap_list, power_insufficient)."""
    aps: list[dict] = []
    power_issue = False
    if not text:
        return None, aps, False

    for line in text.splitlines():
        stripped = line.strip()
        match = _AP_ROW_RE.match(stripped)
        if not match:
            continue
        row = match.groupdict()
        tail = stripped[match.end() :].strip()
        # The ExtraInfo column carries "P" when power supply is insufficient.
        extra = tail.split()[0] if tail.split() else ""
        has_power_flag = "P" in extra.upper() and bool(extra)
        if has_power_flag:
            power_issue = True
        aps.append(
            {
                "id": int(row["id"]),
                "is_leader": bool(row["leader"]),
                "mac": format_mac(row["mac"]),
                "name": row["name"],
                "group": row["group"],
                "zone": row["zone"],
                "ip": row["ip"],
                "model": row["type"],
                "state": row["state"],
                "clients": int(row["sta"]),
                "uptime_seconds": parse_vrp_duration(row["uptime"]),
                "power_insufficient": has_power_flag,
            }
        )

    match = re.search(r"^Total:\s*(\d+)\s*$", text, re.MULTILINE)
    count = int(match.group(1)) if match else (len(aps) or None)
    return count, aps, power_issue


# ---------------------------------------------------------------------------
# display ap power all
# ---------------------------------------------------------------------------
_POWER_ROW_RE = re.compile(
    r"^(?P<id>\d+)\s+"
    r"(?P<mac>[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4})\s+"
    r"(?P<name>\S+)\s+"
    r"(?P<group>\S+)\s+"
    r"(?P<mode>\S+)\s+"
    r"(?P<decided>.+)$"
)


def parse_power(text: str) -> dict[int, dict]:
    """Parse ``display ap power all`` into ``{ap_id: {...}}``.

    Row layout: ID  MAC  Name  Group  Power-workmode  Decided by
    ``Power-workmode`` reports the PoE class the PD chip actually negotiated,
    e.g. ``AF(Limited)`` when the AP wants 802.3at but only got 802.3af.
    """
    result: dict[int, dict] = {}
    if not text:
        return result

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("-") or stripped.startswith("Total:"):
            continue
        match = _POWER_ROW_RE.match(stripped)
        if not match:
            continue
        row = match.groupdict()
        mode = row["mode"]
        result[int(row["id"])] = {
            "mac": format_mac(row["mac"]),
            "name": row["name"],
            "power_mode": mode,
            "power_decided_by": row["decided"].strip(),
            "power_limited": "limited" in mode.lower(),
        }
    return result


# ---------------------------------------------------------------------------
# display radio all
# ---------------------------------------------------------------------------
_RADIO_RE = re.compile(
    r"^(?P<ap_id>\d+)\s+"
    r"(?P<name>\S+)\s+"
    r"(?P<rfid>\d+)\s+"
    r"(?P<band>\S+)\s+"
    r"(?P<type>\S+)\s+"
    r"(?P<status>on|off)\s+"
    r"(?P<channel>\d+/\d+M)\s+"
    r"(?P<eirp>\d+/\d+)\s+"
    r"(?P<sta>\d+)\s+"
    r"(?P<cu>\d+)%\s+"
    r"(?P<mode>\S+)"
)


def parse_radios(text: str) -> list[dict]:
    radios: list[dict] = []
    if not text:
        return radios
    for line in text.splitlines():
        match = _RADIO_RE.match(line.strip())
        if not match:
            continue
        row = match.groupdict()
        channel, _, bandwidth = row["channel"].partition("/")
        radios.append(
            {
                "ap_id": int(row["ap_id"]),
                "ap_name": row["name"],
                "radio_id": int(row["rfid"]),
                "band": row["band"],
                "phy": row["type"],
                "enabled": row["status"].lower() == "on",
                "channel": _safe_int(channel),
                "bandwidth": bandwidth,
                "eirp": row["eirp"],
                "clients": int(row["sta"]),
                "channel_utilization": int(row["cu"]),
                "mode": row["mode"],
            }
        )
    return radios


# ---------------------------------------------------------------------------
# display interface brief
# ---------------------------------------------------------------------------
_INTERFACE_RE = re.compile(
    r"^(?P<name>[A-Za-z][\w/.:-]*)\s+"
    r"(?P<phy>up|down|\*down)\s+"
    r"(?P<proto>up\(s\)|up|down|\*down)\s+"
    r"(?P<inuti>[\d.]+%|--)\s+"
    r"(?P<oututi>[\d.]+%|--)\s+"
    r"(?P<inerr>\d+)\s+"
    r"(?P<outerr>\d+)"
)


def parse_interfaces(text: str) -> list[dict]:
    interfaces: list[dict] = []
    if not text:
        return interfaces
    for line in text.splitlines():
        match = _INTERFACE_RE.match(line.strip())
        if not match:
            continue
        row = match.groupdict()
        interfaces.append(
            {
                "name": row["name"],
                "phy": row["phy"],
                "protocol": row["proto"],
                "up": row["phy"] == "up" and row["proto"].startswith("up"),
                "in_utilization": _parse_pct(row["inuti"]),
                "out_utilization": _parse_pct(row["oututi"]),
                "in_errors": _safe_int(row["inerr"]),
                "out_errors": _safe_int(row["outerr"]),
            }
        )
    return interfaces


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _safe_int(value: str | None) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _parse_pct(value: str) -> float | None:
    if not value or value == "--":
        return None
    try:
        return float(value.rstrip("%"))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# aggregate
# ---------------------------------------------------------------------------
def build_snapshot(
    outputs: dict[str, str], *, ip_address: str | None = None
) -> HuaweiApClientData:
    """Fold raw CLI output into a normalised snapshot."""
    data = HuaweiApClientData(ip_address=ip_address)
    data.raw = {key: value[:6000] for key, value in outputs.items() if value}

    if outputs.get("version"):
        info = parse_version(outputs["version"])
        data.model = info["model"]
        data.firmware = info["firmware"]
        data.serial = info["serial"]
        data.work_mode = info["work_mode"]
        data.uptime_seconds = info["uptime_seconds"]

    if outputs.get("cpu"):
        data.cpu_percent, data.cpu_max_percent = parse_cpu(outputs["cpu"])

    if outputs.get("memory"):
        (
            data.memory_percent,
            data.memory_total_kb,
            data.memory_used_kb,
        ) = parse_memory(outputs["memory"])

    if outputs.get("temperature"):
        (
            data.temperature_max,
            data.temperature,
            data.temperature_alarm,
        ) = parse_temperature(outputs["temperature"])

    if outputs.get("clients"):
        counts, clients = parse_stations(outputs["clients"])
        data.clients = clients
        data.client_count = counts["total"]
        data.client_count_24g = counts["2.4G"]
        data.client_count_5g = counts["5G"]
        data.client_count_6g = counts["6G"]

    if outputs.get("aps"):
        count, aps, power_issue = parse_aps(outputs["aps"])
        data.ap_count = count
        data.aps = aps
        data.power_insufficient = power_issue

        # Enrich each AP with the negotiated PoE class, when available.
        if outputs.get("power"):
            power_map = parse_power(outputs["power"])
            limited = 0
            for ap in aps:
                info = power_map.get(ap["id"])
                if not info:
                    continue
                ap["power_mode"] = info["power_mode"]
                ap["power_decided_by"] = info["power_decided_by"]
                if info["power_limited"]:
                    limited += 1
                    ap["power_insufficient"] = True
            data.power_limited_count = limited
            if limited:
                data.power_insufficient = True

        for ap in aps:
            if ap.get("is_leader"):
                data.mac = ap.get("mac")
                data.hostname = ap.get("name")
                data.ip_address = ap.get("ip") or data.ip_address
                break
        if not data.hostname and aps:
            data.hostname = aps[0].get("name")

    if outputs.get("radios"):
        data.radios = parse_radios(outputs["radios"])

    if outputs.get("interfaces"):
        data.interfaces = parse_interfaces(outputs["interfaces"])

    return data
