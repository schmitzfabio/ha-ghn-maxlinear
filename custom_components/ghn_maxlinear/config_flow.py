"""Config-Flow: manuell ODER per DHCP-Discovery; Passwort kommt aus der UI."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from .api import GhnAuthError, GhnClient, GhnConnectionError
from .const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)


class GhnConfigFlow(ConfigFlow, domain=DOMAIN):
    """Einrichtung eines G.hn-Adapters."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> GhnOptionsFlow:
        return GhnOptionsFlow()

    def __init__(self) -> None:
        self._host: str | None = None
        self._name: str | None = None

    async def _validate(self, host: str, password: str) -> dict:
        """Login testen und Gerätedaten zurückgeben (wirft GhnError)."""
        client = GhnClient(host, password, async_get_clientsession(self.hass))
        return await client.async_get_data()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                data = await self._validate(
                    user_input[CONF_HOST], user_input[CONF_PASSWORD]
                )
            except GhnAuthError:
                errors["base"] = "invalid_auth"
            except GhnConnectionError:
                errors["base"] = "cannot_connect"
            else:
                # MAC identisch normalisieren wie im DHCP-Pfad, sonst legt
                # dasselbe Gerät je nach Einrichtungsweg zwei Einträge an.
                if mac := data.get("mac"):
                    await self.async_set_unique_id(format_mac(mac))
                    self._abort_if_unique_id_configured()
                else:
                    # Ohne MAC keine stabile ID – wenigstens den Host sperren.
                    self._async_abort_entries_match(
                        {CONF_HOST: user_input[CONF_HOST]}
                    )
                title = (
                    user_input.get(CONF_NAME)
                    or f"G.hn {user_input[CONF_HOST]}"
                )
                return self.async_create_entry(title=title, data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_NAME): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Host/Passwort eines bestehenden Eintrags ändern."""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            try:
                data = await self._validate(
                    user_input[CONF_HOST], user_input[CONF_PASSWORD]
                )
            except GhnAuthError:
                errors["base"] = "invalid_auth"
            except GhnConnectionError:
                errors["base"] = "cannot_connect"
            else:
                # Unter der alten IP darf kein anderes Gerät stehen.
                if mac := data.get("mac"):
                    await self.async_set_unique_id(format_mac(mac))
                    self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input
                )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_HOST, default=entry.data[CONF_HOST]
                ): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(
            step_id="reconfigure", data_schema=schema, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Passwort am Gerät geändert – neu abfragen."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            try:
                await self._validate(
                    entry.data[CONF_HOST], user_input[CONF_PASSWORD]
                )
            except GhnAuthError:
                errors["base"] = "invalid_auth"
            except GhnConnectionError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
            description_placeholders={"host": entry.data[CONF_HOST]},
        )

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> ConfigFlowResult:
        """Vom DHCP-Sniffer/Netzwerk-Scan entdeckt."""
        await self.async_set_unique_id(format_mac(discovery_info.macaddress))
        self._abort_if_unique_id_configured(
            updates={CONF_HOST: discovery_info.ip}
        )
        self._host = discovery_info.ip
        self._name = discovery_info.hostname or None
        # Hübscher Name im "Entdeckt"-Kärtchen.
        self.context["title_placeholders"] = {
            "name": self._name or self._host
        }
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Bei Discovery nur noch Passwort abfragen."""
        errors: dict[str, str] = {}
        assert self._host is not None

        if user_input is not None:
            try:
                await self._validate(self._host, user_input[CONF_PASSWORD])
            except GhnAuthError:
                errors["base"] = "invalid_auth"
            except GhnConnectionError:
                errors["base"] = "cannot_connect"
            else:
                title = user_input.get(CONF_NAME) or self._name or f"G.hn {self._host}"
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_HOST: self._host,
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_NAME: title,
                    },
                )

        schema = vol.Schema(
            {
                vol.Optional(CONF_NAME, default=self._name or ""): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(
            step_id="discovery_confirm",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "host": self._host,
                "name": self._name or self._host,
            },
        )


class GhnOptionsFlow(OptionsFlow):
    """Poll-Intervall nachträglich anpassen."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
