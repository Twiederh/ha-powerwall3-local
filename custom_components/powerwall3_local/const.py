"""Constants for the Powerwall 3 Local integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "powerwall3_local"
MANUFACTURER = "Tesla"
MODEL = "Powerwall 3"

CONF_CONNECTION_TYPE = "connection_type"
CONF_GW_PASSWORD = "gw_password"
CONF_RSA_KEY_PATH = "rsa_key_path"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_GROUPS = "groups"  # options: [{"id": str, "name": str, "strings": [str, ...]}]
CONF_GROUP_NAME = "name"
CONF_GROUP_STRINGS = "strings"
CONF_GROUP_ID = "group_id"

# Fallback list when the options flow runs without live data
ALL_STRINGS = ["A", "B", "C", "D", "E", "F"]

CONNECTION_V1R = "v1r"
CONNECTION_WIFI = "wifi"

DEFAULT_WIFI_HOST = "192.168.91.1"
DEFAULT_SCAN_INTERVAL = 10  # seconds
MIN_SCAN_INTERVAL = 5
MAX_SCAN_INTERVAL = 300

# Energy integration: gaps longer than this are not integrated (no data = no energy)
MAX_INTEGRATION_GAP = timedelta(minutes=5)

# Persistent storage for the energy counters
STORAGE_VERSION = 1
STORAGE_SAVE_DELAY = 60  # seconds

# Key used for the sum over all PV strings
TOTAL_KEY = "total"
