from homeassistant.helpers import discovery
from .const import DOMAIN

async def async_setup_entry(hass, entry):
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data

    hass.async_create_task(
        discovery.async_load_platform(hass, "sensor", DOMAIN, entry.data, entry)
    )

    return True