"""Data update coordinator for the Huawei Access Point integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    HuaweiApClientData,
)
from .parser import build_snapshot
from .ssh_client import (
    HuaweiApAuthError,
    HuaweiApCommandError,
    HuaweiApConnectionError,
    HuaweiApError,
    HuaweiApSshClient,
)

_LOGGER = logging.getLogger(__name__)


class HuaweiApCoordinator(DataUpdateCoordinator[HuaweiApClientData]):
    """Polls the AP over SSH and keeps the latest snapshot."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: HuaweiApSshClient,
    ) -> None:
        interval = entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({client.host})",
            update_interval=timedelta(seconds=interval),
        )
        self.client = client
        self.entry = entry
        self.last_errors: dict[str, str] = {}

    async def _async_update_data(self) -> HuaweiApClientData:
        try:
            outputs, errors = await self.client.async_collect()
        except HuaweiApAuthError as err:
            raise UpdateFailed(f"SSH 认证失败: {err}") from err
        except HuaweiApConnectionError as err:
            raise UpdateFailed(f"无法连接设备: {err}") from err
        except HuaweiApCommandError as err:
            raise UpdateFailed(f"命令执行失败: {err}") from err
        except HuaweiApError as err:
            raise UpdateFailed(str(err)) from err

        if self.last_errors != errors:
            if errors:
                _LOGGER.debug("部分命令不可用: %s", errors)
            self.last_errors = errors

        snapshot = build_snapshot(outputs, ip_address=self.client.host)
        snapshot.capabilities = {
            "commands_ok": sorted(outputs),
            "commands_failed": errors,
        }
        return snapshot

    # ------------------------------------------------------------------
    async def async_restart_device(self) -> bool:
        """Reboot the AP. VRP asks for confirmation, which we answer."""
        try:
            await self.client.async_reboot()
        except HuaweiApError as err:
            _LOGGER.error("重启命令失败: %s", err)
            return False
        _LOGGER.warning("已向 %s 发送重启命令", self.client.host)
        return True
