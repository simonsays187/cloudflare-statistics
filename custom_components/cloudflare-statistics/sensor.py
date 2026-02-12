import requests
from datetime import timedelta
from homeassistant.components.sensor import SensorEntity
from homeassistant.util import Throttle
from .const import DOMAIN, CONF_ZONE_ID, CONF_API_TOKEN, CONF_SCAN_INTERVAL

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=60)

SENSOR_TYPES = {
    "pageviews": "Pageviews Today",
    "unique_visitors": "Unique Visitors Today",
    "bots": "Bots Today",
    "threats": "Threats Today",
    "cached_requests": "Cached Requests Today",
}

def setup_platform(hass, config, add_entities, discovery_info=None):
    if discovery_info is None:
        return

    zone_id = discovery_info[CONF_ZONE_ID]
    api_token = discovery_info[CONF_API_TOKEN]
    scan_interval = discovery_info.get(CONF_SCAN_INTERVAL, 300)

    api = CloudflareAPI(zone_id, api_token, scan_interval)

    sensors = [
        CloudflareSensor(api, key, name)
        for key, name in SENSOR_TYPES.items()
    ]

    add_entities(sensors, True)

class CloudflareAPI:
    def __init__(self, zone_id, api_token, scan_interval):
        self.zone_id = zone_id
        self.api_token = api_token
        self.scan_interval = scan_interval
        self.data = {}

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        url = f"https://api.cloudflare.com/client/v4/zones/{self.zone_id}/analytics/dashboard"
        headers = {"Authorization": f"Bearer {self.api_token}"}

        response = requests.get(url, headers=headers, timeout=10)
        json_data = response.json()

        totals = json_data["result"]["totals"]

        self.data = {
            "pageviews": totals["requests"]["all"],
            "unique_visitors": totals["uniques"]["all"],
            "bots": totals["requests"]["bot"],
            "threats": totals["threats"]["all"],
            "cached_requests": totals["requests"]["cached"],
        }

class CloudflareSensor(SensorEntity):
    def __init__(self, api, key, name):
        self.api = api
        self._key = key
        self._attr_name = f"Cloudflare {name}"
        self._state = None

    def update(self):
        self.api.update()
        self._state = self.api.data.get(self._key)

    @property
    def native_value(self):
        return self._state