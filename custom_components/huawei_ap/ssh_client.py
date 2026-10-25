"""Async SSH (Huawei VRP CLI) client for the Huawei Access Point integration.

Why SSH instead of the Web UI: the AP permits a single Web session
(``ErrorMsg=1012`` on the second login) and rejected the cookie issued by
``/login.cgi`` on ``/config.cgi`` (HTTP 450). SSH has neither limitation.

Device quirk that matters: VRP returns an **empty body** on a bare SSH exec
channel - a PTY must be allocated. Every command therefore runs inside a
``vt100`` terminal, which echoes the prompt and the command back. The output
splitter below strips that framing.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import asyncssh

from .const import (
    CLI_CANDIDATES,
    SCREEN_LENGTH_CMD,
    SSH_COMMAND_TIMEOUT,
    SSH_CONNECT_TIMEOUT,
    SSH_HOST_KEY_ALGS,
    SSH_KEX_ALGS,
)

_LOGGER = logging.getLogger(__name__)

# Terminal control sequences the device interleaves with the text.
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07|\r")

# VRP reports command problems with these prefixes.
_COMMAND_ERROR_RE = re.compile(
    r"^\s*(\^|\s*\^)?\s*Error:\s*(Unrecognized|Ambiguous|Incomplete|Wrong)\s+command",
    re.IGNORECASE | re.MULTILINE,
)
_ERROR_HINT_RE = re.compile(r"^\s*Error:\s*(.+)$", re.MULTILINE)


class HuaweiApError(Exception):
    """Base error."""


class HuaweiApAuthError(HuaweiApError):
    """Bad credentials."""


class HuaweiApConnectionError(HuaweiApError):
    """Host unreachable / SSH negotiation failed."""


class HuaweiApCommandError(HuaweiApError):
    """A CLI command returned an error."""


def normalise_host(host: str) -> str:
    host = host.strip()
    host = re.sub(r"^\w+://", "", host)
    host = host.split("/")[0]
    if host.count(":") == 1:
        host = host.split(":")[0]
    return host


class HuaweiApSshClient:
    """Runs a batch of ``display`` commands over one SSH connection."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        *,
        port: int = 22,
        connect_timeout: int = SSH_CONNECT_TIMEOUT,
        command_timeout: int = SSH_COMMAND_TIMEOUT,
    ) -> None:
        self.host = normalise_host(host)
        self.username = username
        self.password = password
        self.port = port
        self.connect_timeout = connect_timeout
        self.command_timeout = command_timeout

    # ------------------------------------------------------------------
    async def _connect(self) -> asyncssh.SSHClientConnection:
        try:
            return await asyncssh.connect(
                self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                known_hosts=None,  # APs use self-signed host keys
                kex_algs=SSH_KEX_ALGS,
                server_host_key_algs=SSH_HOST_KEY_ALGS,
                login_timeout=self.connect_timeout,
                preferred_auth="password",
            )
        except asyncssh.PermissionDenied as err:
            raise HuaweiApAuthError(f"SSH 认证失败: {err}") from err
        except (asyncssh.Error, OSError, asyncio.TimeoutError) as err:
            raise HuaweiApConnectionError(f"SSH 连接失败: {err}") from err

    # ------------------------------------------------------------------
    async def async_run(
        self, commands: list[str], *, timeout: int | None = None
    ) -> tuple[dict[str, str], str]:
        """Execute commands in one PTY session.

        Returns a mapping of command -> cleaned output, plus the raw transcript.
        """
        timeout = timeout or self.command_timeout
        conn = await self._connect()
        try:
            return await asyncio.wait_for(
                self._run_in_pty(conn, commands), timeout=timeout
            )
        except asyncio.TimeoutError as err:
            raise HuaweiApCommandError(
                f"命令执行超时（{timeout}s），设备可能未响应"
            ) from err
        finally:
            conn.close()
            try:
                await conn.wait_closed()
            except Exception:  # noqa: BLE001 - closing must never raise
                pass

    async def _run_in_pty(
        self, conn: asyncssh.SSHClientConnection, commands: list[str]
    ) -> tuple[dict[str, str], str]:
        async with conn.create_process(
            term_type="vt100", encoding="utf-8", errors="replace"
        ) as process:
            # Two device quirks are handled here:
            #  1. long output pages with "---- More ----" unless screen-length
            #     is cleared first, and screen-length needs a moment to apply;
            #  2. the first line typed into a fresh PTY is swallowed by the
            #     terminal setup, so a harmless blank line burns that slot.
            process.stdin.write(f"{SCREEN_LENGTH_CMD}\n")
            await asyncio.sleep(1.2)
            process.stdin.write("\n")
            await asyncio.sleep(0.6)

            for command in commands:
                process.stdin.write(f"{command}\n")
                # Pace the writes: VRP buffers stdin and drops lines when they
                # arrive faster than it can echo a prompt.
                await asyncio.sleep(0.35)

            await asyncio.sleep(0.5)
            process.stdin.write("quit\n")
            process.stdin.write_eof()
            raw = await process.stdout.read()

        raw = _ANSI_RE.sub("", raw or "")
        return self._split(raw, commands), raw

    # ------------------------------------------------------------------
    @staticmethod
    def _split(raw: str, commands: list[str]) -> dict[str, str]:
        """Cut the transcript on echoed command lines."""
        if not raw:
            return {}

        # A VRP prompt looks like "<hostname>" or "<hostname>display version".
        prompt_re = re.compile(
            r"^[^\n]*?>\s*(" + "|".join(re.escape(c) for c in commands) + r")\s*$",
            re.MULTILINE,
        )
        marks = [
            (m.start(), m.end(), m.group(1)) for m in prompt_re.finditer(raw)
        ]

        if not marks:
            # Fallback: the prompt may be customised away - split on the bare
            # command text instead.
            bare_re = re.compile(
                r"^(" + "|".join(re.escape(c) for c in commands) + r")\s*$",
                re.MULTILINE,
            )
            marks = [
                (m.start(), m.end(), m.group(1)) for m in bare_re.finditer(raw)
            ]

        result: dict[str, str] = {}
        for index, (_, end, command) in enumerate(marks):
            stop = marks[index + 1][0] if index + 1 < len(marks) else len(raw)
            body = raw[end:stop]
            # Drop the trailing prompt of the *next* command and quit chatter.
            body = re.sub(r"\n[^\n]*>\s*$", "", body)
            body = body.split("Configuration console exit")[0]
            result[command] = body.strip()
        return result

    # ------------------------------------------------------------------
    @staticmethod
    def command_failed(output: str) -> str | None:
        """Return an error description when the CLI rejected the command."""
        if not output or not output.strip():
            return "命令无输出"
        if _COMMAND_ERROR_RE.search(output):
            match = _ERROR_HINT_RE.search(output)
            return match.group(1).strip() if match else "命令未被识别"
        return None

    # ------------------------------------------------------------------
    async def async_probe(self) -> dict[str, Any]:
        """Login + identity check used by the config flow."""
        outputs, _ = await self.async_run(["display version"], timeout=30)
        version = outputs.get("display version", "")
        error = self.command_failed(version)
        if error:
            raise HuaweiApCommandError(f"已登录但命令被拒绝: {error}")

        info: dict[str, Any] = {"ok": True}
        match = re.search(r"Board\s+Type\s*:\s*(\S+)", version)
        if match:
            info["model"] = match.group(1)
        match = re.search(r"Version\s+([\d.]+)\s*\(([^)]+)\)", version)
        if match:
            info["firmware"] = match.group(1)
            info["firmware_full"] = match.group(2).strip()
        match = re.search(r"^Huawei\s+(\S+)\s+Router\s+uptime", version, re.MULTILINE)
        if match:
            info.setdefault("model", match.group(1))
        return info

    # ------------------------------------------------------------------
    async def async_collect(
        self, categories: list[str] | None = None
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Collect raw CLI output for every requested category.

        Returns ``(outputs_by_category, errors_by_category)``.
        """
        wanted = categories or list(CLI_CANDIDATES)
        # One command per category keeps the request small; fallbacks are tried
        # only when the primary one fails.
        plan: dict[str, str] = {}
        for category in wanted:
            candidates = CLI_CANDIDATES.get(category)
            if candidates:
                plan[candidates[0]] = category

        outputs, raw = await self.async_run(list(plan))

        results: dict[str, str] = {}
        errors: dict[str, str] = {}
        for command, category in plan.items():
            body = outputs.get(command, "")
            failure = self.command_failed(body)
            if failure:
                errors[category] = failure
            else:
                results[category] = body

        # Retry failed categories with their fallback commands.
        retry_plan = {}
        for category, reason in list(errors.items()):
            candidates = CLI_CANDIDATES.get(category, ())
            for fallback in candidates[1:]:
                retry_plan[fallback] = category
        if retry_plan:
            retry_outputs, _ = await self.async_run(list(retry_plan))
            for command, category in retry_plan.items():
                body = retry_outputs.get(command, "")
                if not self.command_failed(body):
                    results[category] = body
                    errors.pop(category, None)

        if not results:
            raise HuaweiApCommandError(
                f"所有命令均失败: {', '.join(f'{k}={v}' for k, v in errors.items())}"
            )
        return results, errors

    # ------------------------------------------------------------------
    async def async_reboot(self) -> None:
        """Reboot the device.

        VRP asks "Are you sure to continue? [Y/N]" on reboot; we answer Y.
        The connection normally dies mid-command, so read errors are ignored.
        """
        conn = await self._connect()
        try:
            async with conn.create_process(
                term_type="vt100", encoding="utf-8", errors="replace"
            ) as process:
                process.stdin.write(f"{SCREEN_LENGTH_CMD}\n")
                await asyncio.sleep(0.3)
                process.stdin.write("reboot\n")
                await asyncio.sleep(1.0)
                process.stdin.write("y\n")
                await asyncio.sleep(0.5)
                process.stdin.write_eof()
                try:
                    await asyncio.wait_for(process.stdout.read(), timeout=6)
                except (asyncio.TimeoutError, asyncssh.Error, OSError):
                    pass
        finally:
            conn.close()
            try:
                await conn.wait_closed()
            except Exception:  # noqa: BLE001
                pass
