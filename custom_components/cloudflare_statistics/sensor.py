import json
import logging
from datetime import datetime, timedelta

import requests
from homeassistant.components.sensor import SensorEntity
from homeassistant.util import Throttle
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    CONF_ZONE_ID,
    CONF_API_TOKEN,
)

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=60)
_LOGGER = logging.getLogger(__name__)

# Sensor definitions
SENSOR_MAP = {
    # Main totals
    "requests_all": ("Requests (All)", lambda d: d.get("requests_all")),
    "requests_cached": ("Requests (Cached)", lambda d: d.get("requests_cached")),
    "requests_uncached": ("Requests (Uncached)", lambda d: d.get("requests_uncached")),
    "requests_threats": ("Threats", lambda d: d.get("requests_threats")),
    "requests_bot": ("Bots", lambda d: d.get("requests_bot")),
    "requests_ssl_encrypted": ("SSL Encrypted Requests", lambda d: d.get("requests_ssl_encrypted")),
    "requests_ssl_unencrypted": ("SSL Unencrypted Requests", lambda d: d.get("requests_ssl_unencrypted")),
    "uniques_all": ("Unique Visitors", lambda d: d.get("uniques_all")),
    "bandwidth_all": ("Bandwidth (All Bytes)", lambda d: d.get("bandwidth_all")),
    "bandwidth_cached": ("Bandwidth (Cached Bytes)", lambda d: d.get("bandwidth_cached")),
    "bandwidth_uncached": ("Bandwidth (Uncached Bytes)", lambda d: d.get("bandwidth_uncached")),

    # HTTP Statuscodes
    "status_200": ("HTTP 200", lambda d: d.get("status_200")),
    "status_301": ("HTTP 301", lambda d: d.get("status_301")),
    "status_404": ("HTTP 404", lambda d: d.get("status_404")),
    "status_500": ("HTTP 500", lambda d: d.get("status_500")),

    # Edge vs Origin
    "edge_requests": ("Edge Response Bytes", lambda d: d.get("edge_requests")),
    "origin_requests": ("Origin Response Bytes", lambda d: d.get("origin_requests")),

    # Live traffic (5 min)
    "live_requests": ("Live Requests (5m)", lambda d: d.get("live_requests")),
    "live_bandwidth": ("Live Bandwidth (5m Bytes)", lambda d: d.get("live_bandwidth")),
    "live_threats": ("Live Threats (5m)", lambda d: d.get("live_threats")),
    "live_bots": ("Live Bots (5m)", lambda d: d.get("live_bots")),
    "live_uniques": ("Live Uniques (5m)", lambda d: d.get("live_uniques")),

    # Top stats (JSON)
    "top_countries": ("Top Countries (JSON)", lambda d: d.get("top_countries")),
    "top_urls": ("Top URLs (JSON)", lambda d: d.get("top_urls")),
    "top_useragents": ("Top User Agents (JSON)", lambda d: d.get("top_useragents")),
}

# GraphQL Queries
# Daily totals (previous 24h)
QUERY_MAIN = """
query ($zoneTag: String!, $start: Date!, $end: Date!) {
    viewer {
        zones(filter: { zoneTag: $zoneTag }) {
            httpRequests1dGroups(
                limit: 1
                filter: { date_geq: $start, date_leq: $end }
            ) {
                sum {
                    requests
                    cachedRequests
                    threats
                    encryptedRequests
                    bytes
                    cachedBytes
                    edgeResponseBytes
                    originResponseBytes
                    status {
                        code
                        count
                    }
                }
                uniq {
                    uniques
                }
            }
        }
    }
}
"""

# Live traffic (rolling 5 minutes)
QUERY_LIVE = """
query ($zoneTag: String!, $start: DateTime!, $end: DateTime!) {
    viewer {
        zones(filter: { zoneTag: $zoneTag }) {
            httpRequestsAdaptiveGroups(
                limit: 1
                filter: { datetime_geq: $start, datetime_leq: $end }
            ) {
                sum {
                    requestCount
                    bytes
                    threatDetectedRequests
                    botDetectedRequests
                }
                uniq {
                    uniques
                }
            }
        }
    }
}
"""

# Top lists for previous 24h
QUERY_TOP = """
query ($zoneTag: String!, $start: Date!, $end: Date!) {
    viewer {
        zones(filter: { zoneTag: $zoneTag }) {
            countries: httpRequests1dGroups(
                limit: 5
                orderBy: [sum_requests_DESC]
                filter: { date_geq: $start, date_leq: $end }
            ) {
                dimensions { clientCountry }
                sum { requests }
            }
            urls: httpRequests1dGroups(
                limit: 5
                orderBy: [sum_requests_DESC]
                filter: { date_geq: $start, date_leq: $end }
            ) {
                dimensions { clientRequestPath }
                sum { requests }
            }
            agents: httpRequests1dGroups(
                limit: 5
                orderBy: [sum_requests_DESC]
                filter: { date_geq: $start, date_leq: $end }
            ) {
                dimensions { userAgent }
                sum { requests }
            }
        }
    }
}
"""


# ---------------------------------------------------------
# NEW: async_setup_entry (replaces setup_platform)
# ---------------------------------------------------------
async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:

    zone_id = entry.data[CONF_ZONE_ID]
    api_token = entry.data[CONF_API_TOKEN]

    api = CloudflareAPI(zone_id, api_token)

    sensors = [
        CloudflareSensor(api, entry.entry_id, key, name, extractor)
        for key, (name, extractor) in SENSOR_MAP.items()
    ]

    async_add_entities(sensors, True)


# ---------------------------------------------------------
# API class (unchanged except for multi-entry compatibility)
# ---------------------------------------------------------
class CloudflareAPI:
    def __init__(self, zone_id, api_token):
        self.zone_id = zone_id
        self.api_token = api_token
        self.data = {}

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        self.data = {}

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        end = datetime.utcnow()
        start = end - timedelta(days=1)
        live_start = end - timedelta(minutes=5)

        start_date = start.date().isoformat()
        end_date = end.date().isoformat()

        # MAIN QUERY
        r1 = requests.post(
            "https://api.cloudflare.com/client/v4/graphql",
            headers=headers,
            data=json.dumps({
                "query": QUERY_MAIN,
                "variables": {
                    "zoneTag": self.zone_id,
                    "start": start_date,
                    "end": end_date,
                },
            }),
            timeout=15,
        ).json()

        if not isinstance(r1, dict):
            _LOGGER.error("Cloudflare main query returned non-dict response")
            r1 = {}

        if r1.get("errors"):
            _LOGGER.error("Cloudflare main query errors: %s", r1.get("errors"))

        try:
            zones = r1.get("data", {}).get("viewer", {}).get("zones") or []
            groups = zones[0].get("httpRequests1dGroups") if zones else None
            if not groups:
                _LOGGER.debug("No main GraphQL data returned")
            else:
                group = groups[0]
                s = group.get("sum", {})
                u = group.get("uniq", {})

                requests_val = s.get("requests") or s.get("requestCount")
                cached_val = s.get("cachedRequests") or 0

                if requests_val is not None:
                    self.data["requests_all"] = requests_val
                    self.data["requests_cached"] = cached_val
                    self.data["requests_uncached"] = requests_val - cached_val

                self.data["requests_threats"] = s.get("threats")
                self.data["requests_ssl_encrypted"] = s.get("encryptedRequests")
                self.data["requests_ssl_unencrypted"] = None

                self.data["bandwidth_all"] = s.get("bytes")
                self.data["bandwidth_cached"] = s.get("cachedBytes")
                if s.get("bytes") is not None and s.get("cachedBytes") is not None:
                    self.data["bandwidth_uncached"] = s.get("bytes") - s.get("cachedBytes")

                self.data["uniques_all"] = u.get("uniques")

                for status in s.get("status", []):
                    code = status.get("code")
                    count = status.get("count")
                    if code is not None:
                        self.data[f"status_{code}"] = count

                self.data["edge_requests"] = s.get("edgeResponseBytes")
                self.data["origin_requests"] = s.get("originResponseBytes")

        except Exception as e:
            _LOGGER.exception("Error parsing main GraphQL: %s", e)

        # LIVE QUERY
        r2 = requests.post(
            "https://api.cloudflare.com/client/v4/graphql",
            headers=headers,
            data=json.dumps({
                "query": QUERY_LIVE,
                "variables": {
                    "zoneTag": self.zone_id,
                    "start": live_start.isoformat(timespec="seconds") + "Z",
                    "end": end.isoformat(timespec="seconds") + "Z",
                },
            }),
            timeout=15,
        ).json()

        if not isinstance(r2, dict):
            _LOGGER.error("Cloudflare live query returned non-dict response")
            r2 = {}

        if r2.get("errors"):
            _LOGGER.error("Cloudflare live query errors: %s", r2.get("errors"))

        try:
            zones = r2.get("data", {}).get("viewer", {}).get("zones") or []
            groups = zones[0].get("httpRequestsAdaptiveGroups") if zones else None
            if not groups:
                _LOGGER.debug("No live GraphQL data returned")
            else:
                live = groups[0]
                s = live.get("sum", {})
                u = live.get("uniq", {})

                requests_val = s.get("requestCount") or s.get("requests")
                bots_val = s.get("botDetectedRequests") or s.get("botRequests")
                threats_val = s.get("threatDetectedRequests") or s.get("threats")

                self.data["live_requests"] = requests_val
                self.data["live_bandwidth"] = s.get("bytes")
                self.data["live_threats"] = threats_val
                self.data["live_bots"] = bots_val
                self.data["live_uniques"] = u.get("uniques")

        except Exception as e:
            _LOGGER.exception("Error parsing live GraphQL: %s", e)

        # TOP QUERY
        r3 = requests.post(
            "https://api.cloudflare.com/client/v4/graphql",
            headers=headers,
            data=json.dumps({
                "query": QUERY_TOP,
                "variables": {
                    "zoneTag": self.zone_id,
                    "start": start_date,
                    "end": end_date,
                },
            }),
            timeout=15,
        ).json()

        if not isinstance(r3, dict):
            _LOGGER.error("Cloudflare top query returned non-dict response")
            r3 = {}

        if r3.get("errors"):
            _LOGGER.error("Cloudflare top query errors: %s", r3.get("errors"))

        try:
            zones = r3.get("data", {}).get("viewer", {}).get("zones") or []
            if not zones:
                _LOGGER.debug("No top GraphQL data returned")
            else:
                zone = zones[0]

                self.data["top_countries"] = json.dumps([
                    {
                        "country": item.get("dimensions", {}).get("clientCountryName"),
                        "requests": item.get("sum", {}).get("requests") or item.get("sum", {}).get("requestCount"),
                    }
                    for item in zone.get("countries", [])
                ])

                self.data["top_urls"] = json.dumps([
                    {
                        "url": item.get("dimensions", {}).get("clientRequestPath"),
                        "requests": item.get("sum", {}).get("requests") or item.get("sum", {}).get("requestCount"),
                    }
                    for item in zone.get("urls", [])
                ])

                self.data["top_useragents"] = json.dumps([
                    {
                        "agent": item.get("dimensions", {}).get("userAgent"),
                        "requests": item.get("sum", {}).get("requests") or item.get("sum", {}).get("requestCount"),
                    }
                    for item in zone.get("agents", [])
                ])

        except Exception as e:
            _LOGGER.exception("Error parsing top GraphQL: %s", e)


# ---------------------------------------------------------
# Sensor Entity (now multi-entry aware)
# ---------------------------------------------------------
class CloudflareSensor(SensorEntity):
    def __init__(self, api, entry_id, key, name, extractor):
        self.api = api
        self._key = key
        self._extractor = extractor
        self._attr_name = f"Cloudflare {name}"
        self._attr_unique_id = f"cloudflare_{entry_id}_{key}"
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