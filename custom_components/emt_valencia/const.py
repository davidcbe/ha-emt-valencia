"""Constants for the EMT València integration."""

from datetime import timedelta

DOMAIN = "emt_valencia"
PLATFORMS = ["sensor", "button"]

CONF_STOP_ID = "stop_id"  # Legacy 0.1 config-entry field.
CONF_DEVICE_TRACKERS = "device_trackers"
CONF_MOBILE_DEVICES = "mobile_devices"
CONF_FAVORITE_STOPS = "favorite_stops"
CONF_SEARCH_RADIUS = "search_radius"
CONF_MAX_NEARBY_STOPS = "max_nearby_stops"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_HOME_SCAN_INTERVAL = "home_scan_interval"
CONF_AWAY_SCAN_INTERVAL = "away_scan_interval"
CONF_FAVORITES_SCAN_INTERVAL = "favorites_scan_interval"
CONF_MOVEMENT_THRESHOLD = "movement_threshold"

DEFAULT_SCAN_INTERVAL = timedelta(minutes=1)  # Legacy option, kept for old entries.
DEFAULT_HOME_SCAN_INTERVAL = 300
DEFAULT_AWAY_SCAN_INTERVAL = 60
DEFAULT_FAVORITES_SCAN_INTERVAL = 300
DEFAULT_SEARCH_RADIUS = 300
DEFAULT_MAX_NEARBY_STOPS = 3
DEFAULT_MOVEMENT_THRESHOLD = 100
MIN_SCAN_INTERVAL = 60
MAX_SCAN_INTERVAL = 600
REQUEST_TIMEOUT = 12
MAX_BACKOFF = 300

ATTR_ARRIVALS = "arrivals"
ATTR_STOP_ID = "stop_id"
ATTR_NEARBY_STOPS = "nearby_stops"
ATTR_DISTANCE = "distance_m"
ATTR_LOCATION = "location"
ATTR_LAST_SUCCESS = "last_successful_update"

