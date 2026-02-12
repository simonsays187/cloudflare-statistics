import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN, CONF_ZONE_ID, CONF_API_TOKEN, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL

class CloudflareConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="Cloudflare Stats", data=user_input)

        schema = vol.Schema({
            vol.Required(CONF_ZONE_ID): str,
            vol.Required(CONF_API_TOKEN): str,
            vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): int,
        })

        return self.async_show_form(step_id="user", data_schema=schema)