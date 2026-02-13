import voluptuous as vol
from homeassistant import config_entries
from .const import (
    DOMAIN,
    CONF_ZONE_ID,
    CONF_API_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_BANDWIDTH_UNIT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_BANDWIDTH_UNIT,
    BANDWIDTH_UNITS,
)

class CloudflareStatisticsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="Cloudflare Statistics", data=user_input)

        schema = vol.Schema({
            vol.Required(CONF_ZONE_ID): str,
            vol.Required(CONF_API_TOKEN): str,
            vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): int,
            vol.Optional(CONF_BANDWIDTH_UNIT, default=DEFAULT_BANDWIDTH_UNIT): vol.In(BANDWIDTH_UNITS),
        })

        return self.async_show_form(step_id="user", data_schema=schema)