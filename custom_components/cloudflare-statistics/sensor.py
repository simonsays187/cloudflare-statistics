import requests
import json
from datetime import datetime, timedelta
from homeassistant.components.sensor import SensorEntity
from homeassistant.util import Throttle
from .const import DOMAIN, CONF_ZONE_ID, CONF_API_TOKEN

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=60)

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
QUERY_MAIN = """
query($zoneTag: String!, $start: Time!, $end: Time!) {
  viewer {
    zones(filter: {zoneTag: $zoneTag}) {
      httpRequests1dGroups(
        limit: 1
        filter: {datetime_geq: $start, datetime_lt: $end}
      ) {
        sum {
          requests
          cachedRequests
          cachedBytes
          bytes
          threats
          encryptedRequests
          unencryptedRequests
          status {
            code
            count
          }
          edgeResponseBytes
          originResponseBytes
        }
        uniq {
          uniques
        }
      }
    }
  }
}
"""

QUERY_LIVE = """
query($zoneTag: String!) {
  viewer {
    zones(filter: {zoneTag: $zoneTag}) {
      httpRequestsAdaptiveGroups(
        limit: 1
        filter: {interval: "5_MINUTE"}
      ) {
        sum {
          requests
          bytes
          threats
          botRequests
        }
        uniq {
          uniques
        }
      }
    }
  }
}
"""

QUERY_TOP = """
query($zoneTag: String!) {
  viewer {
    zones(filter: {zoneTag: $zoneTag}) {

      # Top Countries
      countries: httpRequests1dGroups(
        limit: 10
        orderBy: [sum_requests_DESC]
        filter: {dimensions: ["clientCountryName"]}
      ) {
        dimensions { clientCountryName }
        sum { requests }
      }

      # Top URLs
      urls: httpRequests1dGroups(
        limit: 10
        orderBy: [sum_requests_DESC]
        filter: {dimensions: ["clientRequestPath"]}
      ) {
        dimensions { clientRequestPath }
        sum { requests }
      }

      # Top User Agents
      agents: httpRequests1dGroups(
        limit: 10
        orderBy: [sum_requests_DESC]
        filter: {dimensions: ["userAgent"]}
      ) {
        dimensions { userAgent }
        sum { requests }
      }
    }
  }
}
"""

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
        self.data = {}

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        end = datetime.utcnow()
        start = end - timedelta(days=1)

        # MAIN QUERY
        r1 = requests.post(
            "https://api.cloudflare.com/client/v4/graphql",
            headers=headers,
            data=json.dumps({
                "query": QUERY_MAIN,
                "variables": {
                    "zoneTag": self.zone_id,
                    "start": start.isoformat(timespec="seconds") + "Z",
                    "end": end.isoformat(timespec="seconds") + "Z",
                },
            }),
            timeout=15,
        ).json()

        try:
            group = r1["data"]["viewer"]["zones"][0]["httpRequests1dGroups"][0]
            s = group["sum"]
            u = group["uniq"]

            self.data["requests_all"] = s["requests"]
            self.data["requests_cached"] = s["cachedRequests"]
            self.data["requests_uncached"] = s["requests"] - s["cachedRequests"]
            self.data["requests_threats"] = s["threats"]
            self.data["requests_ssl_encrypted"] = s["encryptedRequests"]
            self.data["requests_ssl_unencrypted"] = s["unencryptedRequests"]

            self.data["bandwidth_all"] = s["bytes"]
            self.data["bandwidth_cached"] = s["cachedBytes"]
            self.data["bandwidth_uncached"] = s["bytes"] - s["cachedBytes"]

            self.data["uniques_all"] = u["uniques"]

            for status in s["status"]:
                code = status["code"]
                count = status["count"]
                self.data[f"status_{code}"] = count

            self.data["edge_requests"] = s["edgeResponseBytes"]
            self.data["origin_requests"] = s["originResponseBytes"]

        except Exception as e:
            print("Error parsing main GraphQL:", e, r1)

        # LIVE QUERY
        r2 = requests.post(
            "https://api.cloudflare.com/client/v4/graphql",
            headers=headers,
            data=json.dumps({
                "query": QUERY_LIVE,
                "variables": {"zoneTag": self.zone_id},
            }),
            timeout=15,
        ).json()

        try:
            live = r2["data"]["viewer"]["zones"][0]["httpRequestsAdaptiveGroups"][0]
            s = live["sum"]
            u = live["uniq"]

            self.data["live_requests"] = s["requests"]
            self.data["live_bandwidth"] = s["bytes"]
            self.data["live_threats"] = s["threats"]
            self.data["live_bots"] = s["botRequests"]
            self.data["live_uniques"] = u["uniques"]

        except Exception as e:
            print("Error parsing live GraphQL:", e, r2)

        # TOP QUERY
        r3 = requests.post(
            "https://api.cloudflare.com/client/v4/graphql",
            headers=headers,
            data=json.dumps({
                "query": QUERY_TOP,
                "variables": {"zoneTag": self.zone_id},
            }),
            timeout=15,
        ).json()

        try:
            zones = r3["data"]["viewer"]["zones"][0]

            # Top Countries
            self.data["top_countries"] = json.dumps([
                {
                    "country": item["dimensions"]["clientCountryName"],
                    "requests": item["sum"]["requests"],
                }
                for item in zones["countries"]
            ])

            # Top URLs
            self.data["top_urls"] = json.dumps([
                {
                    "url": item["dimensions"]["clientRequestPath"],
                    "requests": item["sum"]["requests"],
                }
                for item in zones["urls"]
            ])

            # Top User Agents
            self.data["top_useragents"] = json.dumps([
                {
                    "agent": item["dimensions"]["userAgent"],
                    "requests": item["sum"]["requests"],
                }
                for item in zones["agents"]
            ])

        except Exception as e:
            print("Error parsing top GraphQL:", e, r3)


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