import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional

import requests
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfInformation, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import Throttle

from .const import (
    BANDWIDTH_UNITS,
    CONF_API_TOKEN,
    CONF_BANDWIDTH_UNIT,
    CONF_ZONE_ID,
    DOMAIN,
    DEFAULT_BANDWIDTH_UNIT,
)

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=60)
_LOGGER = logging.getLogger(__name__)

UNIT_FACTORS = {
    "B": 1,
    "KB": 1024,
    "MB": 1024**2,
    "GB": 1024**3,
}


def _to_rfc3339(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


QUERY_ANALYTICS = """
query (
    $zoneTag: String!,
    $monthStart: Date!,
    $todayDate: Date!,
    $todayStart: DateTime!,
    $todayEnd: DateTime!,
    $weekStart: DateTime!,
    $monthStartDt: DateTime!
) {
    viewer {
        zones(filter: { zoneTag: $zoneTag }) {
            httpRequests1dGroups(
                limit: 30
                orderBy: [date_ASC]
                filter: { date_geq: $monthStart, date_leq: $todayDate }
            ) {
                dimensions { date }
                sum { requests bytes }
                uniq { uniques }
            }

            countryToday: httpRequestsAdaptiveGroups(
                limit: 2000
                filter: { datetime_geq: $todayStart, datetime_leq: $todayEnd }
                orderBy: [sum_requests_DESC]
            ) {
                dimensions { clientCountryName }
                sum { requests }
            }

            countryWeek: httpRequestsAdaptiveGroups(
                limit: 2000
                filter: { datetime_geq: $weekStart, datetime_leq: $todayEnd }
                orderBy: [sum_requests_DESC]
            ) {
                dimensions { clientCountryName }
                sum { requests }
            }

            countryMonth: httpRequestsAdaptiveGroups(
                limit: 2000
                filter: { datetime_geq: $monthStartDt, datetime_leq: $todayEnd }
                orderBy: [sum_requests_DESC]
            ) {
                dimensions { clientCountryName }
                sum { requests }
            }

            webToday: rumPageloadEventsAdaptiveGroups(
                limit: 1000
                filter: { datetime_geq: $todayStart, datetime_leq: $todayEnd }
            ) {
                avg { pageLoadTime }
                sum { visits pageViews }
            }

            webWeek: rumPageloadEventsAdaptiveGroups(
                limit: 1000
                filter: { datetime_geq: $weekStart, datetime_leq: $todayEnd }
            ) {
                avg { pageLoadTime }
                sum { visits pageViews }
            }

            webMonth: rumPageloadEventsAdaptiveGroups(
                limit: 1000
                filter: { datetime_geq: $monthStartDt, datetime_leq: $todayEnd }
            ) {
                avg { pageLoadTime }
                sum { visits pageViews }
            }
        }
    }
}
"""


class CloudflareSensorDescription:
    def __init__(
        self,
        key: str,
        name: str,
        value_fn: Callable[[Dict[str, Any]], Any],
        unit: Optional[str] = None,
        device_class: Optional[SensorDeviceClass] = None,
        state_class: Optional[SensorStateClass] = SensorStateClass.MEASUREMENT,
        attr_fn: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
        icon: Optional[str] = None,
    ):
        self.key = key
        self.name = name
        self.value_fn = value_fn
        self.unit = unit
        self.device_class = device_class
        self.state_class = state_class
        self.attr_fn = attr_fn
        self.icon = icon


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    zone_id = entry.data[CONF_ZONE_ID]
    api_token = entry.data[CONF_API_TOKEN]
    bandwidth_unit = entry.data.get(CONF_BANDWIDTH_UNIT, DEFAULT_BANDWIDTH_UNIT)

    api = CloudflareAPI(zone_id, api_token)

    sensors = _build_sensor_definitions(bandwidth_unit)
    entities = [
        CloudflareSensor(api, entry, description)
        for description in sensors
    ]

    async_add_entities(entities, True)


def _build_sensor_definitions(bandwidth_unit: str) -> list[CloudflareSensorDescription]:
    unit_key = bandwidth_unit.upper() if isinstance(bandwidth_unit, str) else DEFAULT_BANDWIDTH_UNIT
    unit_key = unit_key if unit_key in BANDWIDTH_UNITS else DEFAULT_BANDWIDTH_UNIT

    bandwidth_unit_map = {
        "B": UnitOfInformation.BYTES,
        "KB": UnitOfInformation.KILOBYTES,
        "MB": UnitOfInformation.MEGABYTES,
        "GB": UnitOfInformation.GIGABYTES,
    }
    native_unit = bandwidth_unit_map.get(unit_key, UnitOfInformation.MEGABYTES)

    return [
        CloudflareSensorDescription(
            "views_today",
            "Requests Today",
            lambda d: d.get("views_today"),
        ),
        CloudflareSensorDescription(
            "views_week",
            "Requests Week",
            lambda d: d.get("views_week"),
        ),
        CloudflareSensorDescription(
            "views_month",
            "Requests Month",
            lambda d: d.get("views_month"),
        ),
        CloudflareSensorDescription(
            "uniques_today",
            "Unique Visitors Today",
            lambda d: d.get("uniques_today"),
        ),
        CloudflareSensorDescription(
            "uniques_week",
            "Unique Visitors Week",
            lambda d: d.get("uniques_week"),
        ),
        CloudflareSensorDescription(
            "uniques_month",
            "Unique Visitors Month",
            lambda d: d.get("uniques_month"),
        ),
        CloudflareSensorDescription(
            "bandwidth_today",
            "Bandwidth Today",
            lambda d: d.get("bandwidth_today"),
            native_unit,
            SensorDeviceClass.DATA_SIZE,
        ),
        CloudflareSensorDescription(
            "bandwidth_week",
            "Bandwidth Week",
            lambda d: d.get("bandwidth_week"),
            native_unit,
            SensorDeviceClass.DATA_SIZE,
        ),
        CloudflareSensorDescription(
            "bandwidth_month",
            "Bandwidth Month",
            lambda d: d.get("bandwidth_month"),
            native_unit,
            SensorDeviceClass.DATA_SIZE,
        ),
        CloudflareSensorDescription(
            "country_today",
            "Requests by Country Today",
            lambda d: (d.get("country_today") or {}).get("top_requests"),
            state_class=SensorStateClass.MEASUREMENT,
            attr_fn=lambda d: _country_attributes(d.get("country_today")),
            icon="mdi:earth",
        ),
        CloudflareSensorDescription(
            "country_week",
            "Requests by Country Week",
            lambda d: (d.get("country_week") or {}).get("top_requests"),
            state_class=SensorStateClass.MEASUREMENT,
            attr_fn=lambda d: _country_attributes(d.get("country_week")),
            icon="mdi:earth",
        ),
        CloudflareSensorDescription(
            "country_month",
            "Requests by Country Month",
            lambda d: (d.get("country_month") or {}).get("top_requests"),
            state_class=SensorStateClass.MEASUREMENT,
            attr_fn=lambda d: _country_attributes(d.get("country_month")),
            icon="mdi:earth",
        ),
        CloudflareSensorDescription(
            "page_load_today",
            "Page Load Time Today",
            lambda d: (d.get("web_today") or {}).get("page_load_time"),
            UnitOfTime.MILLISECONDS,
            SensorDeviceClass.DURATION,
        ),
        CloudflareSensorDescription(
            "page_load_week",
            "Page Load Time Week",
            lambda d: (d.get("web_week") or {}).get("page_load_time"),
            UnitOfTime.MILLISECONDS,
            SensorDeviceClass.DURATION,
        ),
        CloudflareSensorDescription(
            "page_load_month",
            "Page Load Time Month",
            lambda d: (d.get("web_month") or {}).get("page_load_time"),
            UnitOfTime.MILLISECONDS,
            SensorDeviceClass.DURATION,
        ),
        CloudflareSensorDescription(
            "visits_today",
            "Visits Today",
            lambda d: (d.get("web_today") or {}).get("visits"),
        ),
        CloudflareSensorDescription(
            "visits_week",
            "Visits Week",
            lambda d: (d.get("web_week") or {}).get("visits"),
        ),
        CloudflareSensorDescription(
            "visits_month",
            "Visits Month",
            lambda d: (d.get("web_month") or {}).get("visits"),
        ),
        CloudflareSensorDescription(
            "page_views_today",
            "Page Views Today",
            lambda d: (d.get("web_today") or {}).get("page_views"),
        ),
        CloudflareSensorDescription(
            "page_views_week",
            "Page Views Week",
            lambda d: (d.get("web_week") or {}).get("page_views"),
        ),
        CloudflareSensorDescription(
            "page_views_month",
            "Page Views Month",
            lambda d: (d.get("web_month") or {}).get("page_views"),
        ),
    ]


def _country_attributes(country_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not country_data:
        return {}
    return {
        "top_country": country_data.get("top_country"),
        "countries": country_data.get("countries", {}),
    }


class CloudflareAPI:
    def __init__(self, zone_id: str, api_token: str):
        self.zone_id = zone_id
        self.api_token = api_token
        self.data: Dict[str, Any] = {}

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self) -> None:
        self.data = {}

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        now = datetime.now(timezone.utc)
        today_date = now.date()
        today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        today_end = today_start + timedelta(days=1)
        week_start = today_start - timedelta(days=6)
        month_start = today_start - timedelta(days=29)

        payload = {
            "query": QUERY_ANALYTICS,
            "variables": {
                "zoneTag": self.zone_id,
                "monthStart": month_start.date().isoformat(),
                "todayDate": today_date.isoformat(),
                "todayStart": _to_rfc3339(today_start),
                "todayEnd": _to_rfc3339(today_end),
                "weekStart": _to_rfc3339(week_start),
                "monthStartDt": _to_rfc3339(month_start),
            },
        }

        try:
            resp = requests.post(
                "https://api.cloudflare.com/client/v4/graphql",
                headers=headers,
                data=json.dumps(payload),
                timeout=20,
            )
            result = resp.json()
        except Exception:
            _LOGGER.exception("Cloudflare analytics query failed")
            result = {}

        if not isinstance(result, dict):
            _LOGGER.error("Unexpected Cloudflare response type: %s", type(result))
            return

        if result.get("errors"):
            _LOGGER.error("Cloudflare GraphQL errors: %s", result.get("errors"))

        try:
            zones = result.get("data", {}).get("viewer", {}).get("zones") or []
            zone = zones[0] if zones else {}
            self._parse_requests(zone, today_date, week_start, month_start)
            self._parse_country(zone)
            self._parse_web_analytics(zone)
        except Exception:
            _LOGGER.exception("Failed to parse Cloudflare response")

    def _parse_requests(
        self,
        zone: Dict[str, Any],
        today_date: datetime.date,
        week_start: datetime,
        month_start: datetime,
    ) -> None:
        groups = zone.get("httpRequests1dGroups") or []
        if not groups:
            _LOGGER.debug("No httpRequests1dGroups data returned")
            return

        views_today = views_week = views_month = 0
        uniques_today = uniques_week = uniques_month = 0
        bytes_today = bytes_week = bytes_month = 0

        for item in groups:
            date_str = (item.get("dimensions") or {}).get("date")
            try:
                bucket_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except Exception:
                continue

            sums = item.get("sum", {}) or {}
            uniques = item.get("uniq", {}) or {}

            req = sums.get("requests") or 0
            bts = sums.get("bytes") or 0
            uni = uniques.get("uniques") or 0

            if bucket_date == today_date:
                views_today += req
                uniques_today += uni
                bytes_today += bts
            if week_start.date() <= bucket_date <= today_date:
                views_week += req
                uniques_week += uni
                bytes_week += bts
            if month_start.date() <= bucket_date <= today_date:
                views_month += req
                uniques_month += uni
                bytes_month += bts

        self.data.update({
            "views_today": views_today,
            "views_week": views_week,
            "views_month": views_month,
            "uniques_today": uniques_today,
            "uniques_week": uniques_week,
            "uniques_month": uniques_month,
            "bandwidth_today_bytes": bytes_today,
            "bandwidth_week_bytes": bytes_week,
            "bandwidth_month_bytes": bytes_month,
        })

    def _parse_country(self, zone: Dict[str, Any]) -> None:
        alias_map = {
            "country_today": "countryToday",
            "country_week": "countryWeek",
            "country_month": "countryMonth",
        }

        for key, gql_key in alias_map.items():
            groups = zone.get(gql_key) or []
            self.data[key] = self._summarize_countries(groups)

    @staticmethod
    def _summarize_countries(groups: list[Dict[str, Any]]) -> Dict[str, Any]:
        country_map: Dict[str, int] = {}
        for item in groups or []:
            country = (item.get("dimensions") or {}).get("clientCountryName") or "Unknown"
            requests_count = (item.get("sum") or {}).get("requests") or 0
            country_map[country] = country_map.get(country, 0) + requests_count

        if not country_map:
            return {"top_country": None, "top_requests": None, "countries": {}}

        top_country, top_requests = max(country_map.items(), key=lambda kv: kv[1])
        return {"top_country": top_country, "top_requests": top_requests, "countries": country_map}

    def _parse_web_analytics(self, zone: Dict[str, Any]) -> None:
        for key in ("web_today", "web_week", "web_month"):
            groups = zone.get(key) or []
            visits = 0
            page_views = 0
            load_times = []

            for item in groups:
                sums = item.get("sum") or {}
                avg = item.get("avg") or {}
                visits += sums.get("visits") or 0
                page_views += sums.get("pageViews") or 0
                plt = avg.get("pageLoadTime")
                if plt is not None:
                    load_times.append(plt)

            avg_load = sum(load_times) / len(load_times) if load_times else None

            self.data[key] = {
                "visits": visits,
                "page_views": page_views,
                "page_load_time": avg_load,
            }


class CloudflareSensor(SensorEntity):
    def __init__(self, api: CloudflareAPI, entry: ConfigEntry, description: CloudflareSensorDescription) -> None:
        self.api = api
        self._entry = entry
        self.entity_description = description
        self._attr_name = f"Cloudflare {description.name}"
        self._attr_unique_id = f"cloudflare_{entry.entry_id}_{description.key}"
        self._attr_device_class = description.device_class
        self._attr_native_unit_of_measurement = description.unit
        self._attr_state_class = description.state_class
        self._attr_icon = description.icon
        self._state: Any = None
        self._attributes: Dict[str, Any] = {}

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer="Cloudflare",
            name=f"Cloudflare Zone {self._entry.data.get(CONF_ZONE_ID)}",
            configuration_url=f"https://dash.cloudflare.com/?zone={self._entry.data.get(CONF_ZONE_ID)}",
        )

    def update(self) -> None:
        self.api.update()

        # Convert raw bytes to configured unit when needed
        self._convert_bandwidth()

        try:
            self._state = self.entity_description.value_fn(self.api.data)
        except Exception:
            self._state = None

        if self.entity_description.attr_fn:
            try:
                self._attributes = self.entity_description.attr_fn(self.api.data)
            except Exception:
                self._attributes = {}
        else:
            self._attributes = {}

    @property
    def native_value(self) -> Any:
        return self._state

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        return self._attributes

    def _convert_bandwidth(self) -> None:
        unit = self._attr_native_unit_of_measurement
        if unit is None:
            return

        factor = UNIT_FACTORS.get(unit) if isinstance(unit, str) else None
        if factor is None:
            # Home Assistant constants return objects, not strings
            if unit == UnitOfInformation.BYTES:
                factor = UNIT_FACTORS["B"]
            else:
                return

        for key in ("bandwidth_today", "bandwidth_week", "bandwidth_month"):
            raw_key = f"{key}_bytes"
            if raw_key in self.api.data:
                self.api.data[key] = round(self.api.data[raw_key] / factor, 2)