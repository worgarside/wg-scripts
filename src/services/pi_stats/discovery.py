"""Home Assistant MQTT device discovery for pi_stats sensors."""

from __future__ import annotations

from typing import Any, Final

from wg_scripts import __version__

DISCOVERY_PREFIX: Final = "homeassistant"
PAYLOAD_ONLINE: Final = "online"
PAYLOAD_OFFLINE: Final = "offline"


def path_to_slug(path: str) -> str:
    """Convert a filesystem path to a stable entity-id slug.

    Examples:
        `/` -> `root`
        `/home` -> `home`
        `/mnt/storage` -> `mnt_storage`
    """
    if path == "/":
        return "root"

    normalized = path.strip("/")
    if not normalized:
        return "root"

    return normalized.replace("/", "_").replace("-", "_").lower()


def disk_path_slugs(paths: tuple[str, ...] | list[str]) -> dict[str, str]:
    """Map each disk path to a unique slug, rejecting collisions.

    Returns:
        dict[str, str]: path -> slug mapping in input order.

    Raises:
        ValueError: if two paths normalize to the same slug.
    """
    slugs: dict[str, str] = {}
    slug_owners: dict[str, str] = {}

    for path in paths:
        slug = path_to_slug(path)
        if slug in slug_owners:
            raise ValueError(
                f"Disk path slug collision: {path!r} and {slug_owners[slug]!r} both "
                f"map to {slug!r}",
            )
        slug_owners[slug] = path
        slugs[path] = slug

    return slugs


def availability_topic(hostname: str) -> str:
    """Return the retained availability topic for pi_stats on a host."""
    return f"/homeassistant/{hostname}/pi_stats/availability"


def stats_topic(hostname: str) -> str:
    """Return the JSON state topic for pi_stats on a host."""
    return f"/homeassistant/{hostname}/stats"


def discovery_topic(hostname: str) -> str:
    """Return the retained device-discovery config topic for a host."""
    return f"{DISCOVERY_PREFIX}/device/{hostname}_pi_stats/config"


def _sensor_component(
    *,
    hostname: str,
    metric: str,
    name: str,
    value_template: str,
    icon: str,
    force_update: bool,
    unit_of_measurement: str | None = None,
    state_class: str | None = None,
    device_class: str | None = None,
) -> dict[str, Any]:
    """Build one MQTT sensor component config."""
    unique_id = f"{hostname}_{metric}"
    component: dict[str, Any] = {
        "p": "sensor",
        "name": name,
        "unique_id": unique_id,
        "default_entity_id": f"sensor.{unique_id}",
        "icon": icon,
        "force_update": force_update,
        "value_template": value_template,
    }
    if unit_of_measurement is not None:
        component["unit_of_measurement"] = unit_of_measurement
    if state_class is not None:
        component["state_class"] = state_class
    if device_class is not None:
        component["device_class"] = device_class
    return component


def _fixed_components(hostname: str) -> dict[str, dict[str, Any]]:
    """Build the 12 fixed pi_stats sensor components."""
    sensors: list[dict[str, Any]] = [
        _sensor_component(
            hostname=hostname,
            metric="cpu_usage",
            name="CPU Usage",
            value_template="{{ value_json.cpu_usage }}",
            icon="mdi:cpu-32-bit",
            force_update=True,
            unit_of_measurement="%",
            state_class="measurement",
        ),
        _sensor_component(
            hostname=hostname,
            metric="cpu_temperature",
            name="CPU Temperature",
            value_template="{{ value_json.temperature }}",
            icon="mdi:memory",
            force_update=True,
            unit_of_measurement="°C",
            state_class="measurement",
            device_class="temperature",
        ),
        _sensor_component(
            hostname=hostname,
            metric="memory_usage",
            name="Memory Usage",
            value_template="{{ value_json.memory_usage }}",
            icon="mdi:memory",
            force_update=True,
            unit_of_measurement="%",
            state_class="measurement",
        ),
        _sensor_component(
            hostname=hostname,
            metric="average_load_1_min",
            name="Average Load (1 min)",
            value_template="{{ value_json.load_1m }}",
            icon="mdi:weight",
            force_update=True,
            state_class="measurement",
        ),
        _sensor_component(
            hostname=hostname,
            metric="average_load_5_min",
            name="Average Load (5 min)",
            value_template="{{ value_json.load_5m }}",
            icon="mdi:weight",
            force_update=True,
            state_class="measurement",
        ),
        _sensor_component(
            hostname=hostname,
            metric="average_load_15_min",
            name="Average Load (15 min)",
            value_template="{{ value_json.load_15m }}",
            icon="mdi:weight",
            force_update=True,
            state_class="measurement",
        ),
        _sensor_component(
            hostname=hostname,
            metric="uptime",
            name="Uptime",
            value_template="{{ value_json.uptime }}",
            icon="mdi:timer-cog-outline",
            force_update=False,
            unit_of_measurement="s",
            state_class="measurement",
        ),
        _sensor_component(
            hostname=hostname,
            metric="boot_time",
            name="Boot Time",
            value_template="{{ value_json.boot_time }}",
            icon="mdi:console",
            force_update=False,
            device_class="timestamp",
        ),
        _sensor_component(
            hostname=hostname,
            metric="pi_stats_start_time",
            name="Pi Stats Start Time",
            value_template="{{ value_json.service_start_time }}",
            icon="mdi:console",
            force_update=False,
            device_class="timestamp",
        ),
        _sensor_component(
            hostname=hostname,
            metric="local_git_ref",
            name="Local Git Ref",
            value_template="{{ value_json.local_git_ref }}",
            icon="mdi:source-repository",
            force_update=False,
        ),
        _sensor_component(
            hostname=hostname,
            metric="active_git_ref",
            name="Active Git Ref",
            value_template="{{ value_json.active_git_ref }}",
            icon="mdi:source-branch-sync",
            force_update=False,
        ),
        _sensor_component(
            hostname=hostname,
            metric="local_ip_address",
            name="Local IP Address",
            value_template=(
                f"{{{{ value_json.local_ip | default('{hostname}.local') }}}}"
            ),
            icon="mdi:ip-network-outline",
            force_update=True,
        ),
    ]

    return {component["unique_id"]: component for component in sensors}


def _disk_components(
    hostname: str,
    disk_paths: tuple[str, ...] | list[str],
) -> dict[str, dict[str, Any]]:
    """Build one disk-usage sensor component per configured path."""
    components: dict[str, dict[str, Any]] = {}

    for path, slug in disk_path_slugs(disk_paths).items():
        metric = f"disk_usage_{slug}"
        # Escape single quotes in path for the Jinja literal key.
        jinja_path = path.replace("'", "\\'")
        components[f"{hostname}_{metric}"] = _sensor_component(
            hostname=hostname,
            metric=metric,
            name=f"Disk Usage ({path})",
            value_template=f"{{{{ value_json.disk_usage['{jinja_path}'] }}}}",
            icon="mdi:harddisk",
            force_update=True,
            unit_of_measurement="%",
            state_class="measurement",
        )

    return components


def build_discovery_payload(
    hostname: str,
    disk_paths: tuple[str, ...] | list[str],
    *,
    sw_version: str = __version__,
) -> dict[str, Any]:
    """Build a retained MQTT device-discovery payload for pi_stats.

    Args:
        hostname: Pi hostname used in topics and unique IDs.
        disk_paths: Filesystem paths that appear under `disk_usage` in the state
            payload.
        sw_version: Software version advertised in the discovery origin/device.

    Returns:
        dict[str, Any]: discovery payload ready to JSON-serialize.
    """
    components = _fixed_components(hostname)
    components.update(_disk_components(hostname, disk_paths))

    return {
        "dev": {
            "ids": [f"{hostname}_pi_stats"],
            "name": hostname,
            "mf": "wg-scripts",
            "mdl": "pi_stats",
            "sw": sw_version,
        },
        "o": {
            "name": "wg-scripts/pi_stats",
            "sw": sw_version,
            "url": "https://github.com/worgarside/wg-scripts",
        },
        "cmps": components,
        "state_topic": stats_topic(hostname),
        "availability": [{"topic": availability_topic(hostname)}],
        "payload_available": PAYLOAD_ONLINE,
        "payload_not_available": PAYLOAD_OFFLINE,
        "qos": 1,
    }
