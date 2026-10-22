"""Config flow for Powerwall 3 Local."""

from __future__ import annotations

import logging
import os
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from . import build_client
from .api import PowerwallConnectionError, PowerwallInfo
from .const import (
    CONF_CONNECTION_TYPE,
    CONF_GW_PASSWORD,
    CONF_RSA_KEY_PATH,
    CONF_SCAN_INTERVAL,
    CONNECTION_V1R,
    CONNECTION_WIFI,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_WIFI_HOST,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_RSA_KEY_PATH = "/config/tedapi_rsa_private.pem"


class InvalidKeyPath(Exception):
    """RSA key file missing or unreadable."""


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> PowerwallInfo:
    """Connect once and return the device info."""
    key_path = data.get(CONF_RSA_KEY_PATH)
    if key_path and not await hass.async_add_executor_job(os.access, key_path, os.R_OK):
        raise InvalidKeyPath
    client = build_client(hass, data)
    return await hass.async_add_executor_job(client.get_info)


class Powerwall3LocalConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._connection_type: str = CONNECTION_V1R

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Choose how the Powerwall is reached."""
        if user_input is not None:
            self._connection_type = user_input[CONF_CONNECTION_TYPE]
            return await self.async_step_connection()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CONNECTION_TYPE, default=CONNECTION_V1R): SelectSelector(
                        SelectSelectorConfig(
                            options=[CONNECTION_V1R, CONNECTION_WIFI],
                            mode=SelectSelectorMode.LIST,
                            translation_key=CONF_CONNECTION_TYPE,
                        )
                    )
                }
            ),
        )

    async def async_step_connection(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Host, gateway password and (for v1r) the RSA key."""
        errors: dict[str, str] = {}
        is_v1r = self._connection_type == CONNECTION_V1R

        if user_input is not None:
            data = {
                CONF_CONNECTION_TYPE: self._connection_type,
                CONF_HOST: user_input[CONF_HOST].strip(),
                CONF_GW_PASSWORD: user_input[CONF_GW_PASSWORD].strip(),
                CONF_RSA_KEY_PATH: user_input.get(CONF_RSA_KEY_PATH, "").strip() if is_v1r else "",
            }
            try:
                info = await validate_input(self.hass, data)
            except InvalidKeyPath:
                errors[CONF_RSA_KEY_PATH] = "invalid_key_path"
            except PowerwallConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error while connecting to the Powerwall")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(info.din)
                self._abort_if_unique_id_configured(updates=data)
                title = info.site_name or f"Powerwall 3 ({info.din})"
                return self.async_create_entry(title=title, data=data)

        defaults = user_input or {}
        schema: dict[Any, Any] = {
            vol.Required(
                CONF_HOST,
                default=defaults.get(CONF_HOST, "" if is_v1r else DEFAULT_WIFI_HOST),
            ): TextSelector(),
            vol.Required(CONF_GW_PASSWORD, default=defaults.get(CONF_GW_PASSWORD, "")): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
        }
        if is_v1r:
            schema[
                vol.Required(
                    CONF_RSA_KEY_PATH,
                    default=defaults.get(CONF_RSA_KEY_PATH, DEFAULT_RSA_KEY_PATH),
                )
            ] = TextSelector()

        return self.async_show_form(
            step_id="connection",
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders={"connection_type": self._connection_type},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        """Options: polling interval."""
        return Powerwall3LocalOptionsFlow()


class Powerwall3LocalOptionsFlow(OptionsFlow):
    """Options flow for the scan interval."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL])}
            )

        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=current): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL,
                            max=MAX_SCAN_INTERVAL,
                            step=1,
                            unit_of_measurement="s",
                            mode=NumberSelectorMode.BOX,
                        )
                    )
                }
            ),
        )
