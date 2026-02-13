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
    "views_today": ("Views Today", lambda d: d.get("views_today")),
    "views_week": ("Views Week", lambda d: d.get("views_week")),
    "views_month": ("Views Month", lambda d: d.get("views_month")),
    "uniques_today": ("Uniques Today", lambda d: d.get("uniques_today")),
    "uniques_week": ("Uniques Week", lambda d: d.get("uniques_week")),
    "uniques_month": ("Uniques Month", lambda d: d.get("uniques_month")),
}

# GraphQL Query: per-day buckets (max 30 days back)
QUERY_DAILY = """
query ($zoneTag: String!, $start: Date!, $end: Date!) {
    viewer {
        zones(filter: { zoneTag: $zoneTag }) {
            httpRequests1dGroups(
                limit: 30
                orderBy: [date_ASC]
                filter: { date_geq: $start, date_leq: $end }
            ) {
                dimensions { date }
                sum { requests }
                uniq { uniques }
            }
        }
    }
}
"""


# ---------------------------------------------------------
# async_setup_entry
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
# API class
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

        end = datetime.utcnow().date()
        start_30 = end - timedelta(days=30)

        try:
            r_resp = requests.post(
                "https://api.cloudflare.com/client/v4/graphql",
                headers=headers,
                data=json.dumps({
                    "query": QUERY_DAILY,
                    "variables": {
                        "zoneTag": self.zone_id,
                        "start": start_30.isoformat(),
                        "end": end.isoformat(),
                    },
                }),
                timeout=15,
            )
            r = r_resp.json()
        except Exception:
            _LOGGER.exception("Cloudflare daily query request failed")
            r = {}

        if not isinstance(r, dict):
            _LOGGER.error("Cloudflare daily query returned non-dict response")
            r = {}

        if r.get("errors"):
            _LOGGER.error("Cloudflare daily query errors: %s", r.get("errors"))

        try:
            zones = r.get("data", {}).get("viewer", {}).get("zones") or []
            groups = zones[0].get("httpRequests1dGroups") if zones else None
            if not groups:
                _LOGGER.debug("No daily GraphQL data returned")
                return

            today = end
            week_threshold = end - timedelta(days=6)  # today + previous 6
            month_threshold = end - timedelta(days=29)  # 30 days window

            views_today = 0
            views_week = 0
            views_month = 0
            uniques_today = 0
            uniques_week = 0
            uniques_month = 0

            for item in groups:
                date_str = item.get("dimensions", {}).get("date")
                try:
                    bucket_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                except Exception:
                    continue

                s = item.get("sum", {})
                u = item.get("uniq", {})
                req = s.get("requests") or 0
                uni = u.get("uniques") or 0

                if bucket_date == today:
                    views_today += req
                    uniques_today += uni
                if week_threshold <= bucket_date <= today:
                    views_week += req
                    uniques_week += uni
                if month_threshold <= bucket_date <= today:
                    views_month += req
                    uniques_month += uni

            self.data["views_today"] = views_today
            self.data["views_week"] = views_week
            self.data["views_month"] = views_month
            self.data["uniques_today"] = uniques_today
            self.data["uniques_week"] = uniques_week
            self.data["uniques_month"] = uniques_month

        except Exception as e:
            _LOGGER.exception("Error parsing daily GraphQL: %s", e)


# ---------------------------------------------------------
# Sensor Entity
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