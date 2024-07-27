"""Common Constants and Environment Variables."""

from __future__ import annotations

import re
import socket
import warnings
from os import getenv
from typing import Final

# =============================================================================
# Environment Variables

HOSTNAME: Final[str] = getenv("HOSTNAME", socket.gethostname())
MQTT_USERNAME: Final[str] = getenv("MQTT_USERNAME", HOSTNAME)
MQTT_PASSWORD: Final[str] = getenv("MQTT_PASSWORD", "")
MQTT_HOST: Final[str] = getenv("MQTT_HOST", "homeassistant.local")

if not MQTT_PASSWORD:
    warnings.warn("Environment Variable `MQTT_PASSWORD` is not set", stacklevel=2)


# =============================================================================
# Constants


KEBAB_PATTERN = re.compile(r"^(?:[a-z0-9]+-?)+[a-z0-9]+$")
"""Pattern for `kebab-case` strings."""
