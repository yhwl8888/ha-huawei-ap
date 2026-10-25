"""Huawei Access Point integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_PORT, DEFAULT_PORT, DOMAIN, PLATFORMS
from .coordinator import HuaweiApCoordinator
from .ssh_client import (
    HuaweiApAuthError,
    HuaweiApConnectionError,
    HuaweiApError,
    HuaweiApSshClient,
)

_LOGGER = logging.getLogger(__name__)

type HuaweiApConfigEntry = ConfigEntry[HuaweiApCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: HuaweiApConfigEntry) -> bool:
    """Set up Huawei AP from a config entry."""
    client = HuaweiApSshClient(
        host=entry.data[CONF_HOST],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        port=entry.data.get(CONF_PORT, DEFAULT_PORT),
    )

    coordinator = HuaweiApCoordinator(hass, entry, client)

    try:
        await coordinator.async_config_entry_first_refresh()
    except HuaweiApAuthError as err:
        raise ConfigEntryNotReady(f"认证失败: {err}") from err
    except HuaweiApConnectionError as err:
        raise ConfigEntryNotReady(f"无法连接华为 AP: {err}") from err
    except HuaweiApError as err:
        raise ConfigEntryNotReady(f"初始化失败: {err}") from err

    entry.runtime_data = coordinator
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _LOGGER.info(
        "华为 AP 集成已加载: %s (%s)", client.host, coordinator.data.model
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HuaweiApConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok


async def _async_update_listener(
    hass: HomeAssistant, entry: HuaweiApConfigEntry
) -> None:
    """Reload when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
