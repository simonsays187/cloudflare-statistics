import requests
from datetime import timedelta
from homeassistant.components.sensor import SensorEntity
from homeassistant.util import Throttle
from .const import DOMAIN, CONF_ZONE_ID, CONF_API_TOKEN, CONF_SCAN_INTERVAL

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=60)

SENSOR_MAP = {
    "requests_all": ("Requests (All)", lambda d: d["requests"]["all"]),
    "requests_cached": ("Requests (Cached)", lambda d: d["requests"]["cached"]),
    "requests_uncached": ("Requests (Uncached)", lambda d: d["requests"]["uncached"]),
    "requests_bot": ("Requests (Bots)", lambda d: d["requests"]["bot"]),
    "requests_ssl_encrypted": ("Requests (SSL Encrypted)", lambda d: d["requests"]["ssl"]["encrypted"]),
    "requests_ssl_unencrypted": ("Requests (SSL Unencrypted)", lambda d: d["requests"]["ssl"]["unencrypted"]),
    "uniques_all": ("Unique Visitors", lambda d: d["uniques"]["all"]),
    "threats_all": ("Threats (All)", lambda d: d["threats"]["all"]),
    "threats_blocked": ("Threats (Blocked)", lambda d: d["threats"]["blocked"]),
    "bandwidth_all": ("Bandwidth (All Bytes)", lambda d: d["bandwidth"]["all"]),
    "bandwidth_cached": ("Bandwidth (Cached Bytes)", lambda d: d["bandwidth"]["cached"]),
    "bandwidth_uncached": ("Bandwidth (Uncached Bytes)", lambda d: d["bandwidth"]["uncached"]),
}

def setup_platform(hass, config, add_entities, discovery_info=None):
    if discovery_info is None:
        return

    zone_id = discovery_info[CONF_ZONE_ID]
    api_token = discovery_info[CONF_API_TOKEN]

    api = CloudflareAPI(zone_id, api_token)

    sensors = [
        CloudflareSensor(api, key, name, extractor)
        for key, (name, extractor) in SENSOR_MAP.items()
    ]

    add_entities(sensors, True)


class CloudflareAPI:
    def __init__(self, zone_id, api_token):
        self.zone_id = zone_id
        self.api_token = api_token
        self.data = {}

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        url = f"https://api.cloudflare.com/client/v4/zones/{self.zone_id}/analytics/dashboard"
        headers = {"Authorization": f"Bearer {self.api_token}"}

        response = requests.get(url, headers=headers, timeout=10)
        json_data = response.json()

        self.data = json_data["result"]["totals"]


class CloudflareSensor(SensorEntity):
    def __init__(self, api, key, name, extractor):
        self.api = api
        self._key = key
        self._extractor = extractor
        self._attr_name = f"Cloudflare {name}"
        self._attr_unique_id = f"cloudflare_{key}"
        self._state = None

    def update(self):
        self.api.update()
        try:
            self._state = self._extractor(self.api.data)
        except Exception:
            self._state = None

    @property
    def native_value(self):
        return self._state