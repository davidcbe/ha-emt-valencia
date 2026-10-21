"""Constants for the EMT València integration."""

from datetime import timedelta

DOMAIN = "emt_valencia"
PLATFORMS = ["sensor"]

CONF_STOP_ID = "stop_id"
DEFAULT_STOP_ID = "1622"
DEFAULT_SCAN_INTERVAL = timedelta(minutes=1)

ATTR_ARRIVALS = "arrivals"
ATTR_STOP_ID = "stop_id"

