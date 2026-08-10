"""Home Assistant MQTT device discovery for pi_stats sensors."""

from __future__ import annotations

import re
from dataclasses import dataclass
from json import JSONDecodeError, dumps, loads
from typing import TYPE_CHECKING, Any, Final, Literal

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from services.pi_stats.mount_health import MountCheck

from wg_scripts import __version__

DISCOVERY_PREFIX: Final = "homeassistant"
PAYLOAD_ONLINE: Final = "online"
PAYLOAD_OFFLINE: Final = "offline"
NON_ALPHANUMERIC: Final = re.compile(r"[^a-z0-9]+")
SmartKind = Literal["ata", "nvme"]


@dataclass(frozen=True, slots=True)
class SmartDevice:
    """A SMART-capable block device detected for optional pi_stats sensors."""

    device: str
    transport: str
    kind: SmartKind
    slug: str
    label: str


def path_to_slug(path: str) -> str:
    """Convert a filesystem path to a stable entity-id slug.

    Examples:
        `/` -> `root`
        `/home` -> `home`
        `/mnt/storage` -> `mnt_storage`
    """
    return NON_ALPHANUMERIC.sub("_", path.casefold()).strip("_") or "root"


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
    entity_category: str | None = None,
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
    if entity_category is not None:
        component["entity_category"] = entity_category
    return component


def _binary_sensor_component(
    *,
    hostname: str,
    metric: str,
    name: str,
    value_template: str,
    icon: str,
    force_update: bool,
    payload_on: str,
    payload_off: str,
    device_class: str | None = None,
    entity_category: str | None = None,
) -> dict[str, Any]:
    """Build one MQTT binary_sensor component config."""
    unique_id = f"{hostname}_{metric}"
    component: dict[str, Any] = {
        "p": "binary_sensor",
        "name": name,
        "unique_id": unique_id,
        "default_entity_id": f"binary_sensor.{unique_id}",
        "icon": icon,
        "force_update": force_update,
        "value_template": value_template,
        "payload_on": payload_on,
        "payload_off": payload_off,
    }
    if device_class is not None:
        component["device_class"] = device_class
    if entity_category is not None:
        component["entity_category"] = entity_category
    return component


def _fixed_components(hostname: str) -> dict[str, dict[str, Any]]:
    """Build the fixed pi_stats sensor components."""
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
            metric="cpu_frequency",
            name="CPU Frequency",
            value_template="{{ value_json.cpu_frequency_mhz }}",
            icon="mdi:speedometer",
            force_update=True,
            unit_of_measurement="MHz",
            state_class="measurement",
            device_class="frequency",
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
            metric="swap_usage",
            name="Swap Usage",
            value_template="{{ value_json.swap_usage }}",
            icon="mdi:harddisk",
            force_update=True,
            unit_of_measurement="%",
            state_class="measurement",
        ),
        _sensor_component(
            hostname=hostname,
            metric="cpu_iowait",
            name="CPU I/O Wait",
            value_template="{{ value_json.cpu_iowait }}",
            icon="mdi:timer-sand",
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
            metric="wg_scripts_version",
            name="wg-scripts Version",
            value_template="{{ value_json.wg_scripts_version }}",
            icon="mdi:package-variant-closed",
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
        _sensor_component(
            hostname=hostname,
            metric="network_interface",
            name="Network Interface",
            value_template="{{ value_json.network_interface }}",
            icon="mdi:network-outline",
            force_update=False,
            entity_category="diagnostic",
        ),
        _sensor_component(
            hostname=hostname,
            metric="network_receive",
            name="Network Receive",
            value_template="{{ value_json.network_receive_bytes_per_second }}",
            icon="mdi:download-network",
            force_update=True,
            unit_of_measurement="B/s",
            state_class="measurement",
            device_class="data_rate",
        ),
        _sensor_component(
            hostname=hostname,
            metric="network_transmit",
            name="Network Transmit",
            value_template="{{ value_json.network_transmit_bytes_per_second }}",
            icon="mdi:upload-network",
            force_update=True,
            unit_of_measurement="B/s",
            state_class="measurement",
            device_class="data_rate",
        ),
        _sensor_component(
            hostname=hostname,
            metric="pending_updates",
            name="Pending Updates",
            value_template="{{ value_json.pending_updates }}",
            icon="mdi:package-up",
            force_update=False,
            state_class="measurement",
        ),
        _binary_sensor_component(
            hostname=hostname,
            metric="throttling_active",
            name="Throttling Active",
            value_template=(
                "{% if value_json.throttling_active is defined %}"
                "{{ 'ON' if value_json.throttling_active else 'OFF' }}"
                "{% endif %}"
            ),
            icon="mdi:alert-octagon",
            force_update=True,
            payload_on="ON",
            payload_off="OFF",
            device_class="problem",
        ),
        _binary_sensor_component(
            hostname=hostname,
            metric="throttling_occurred",
            name="Throttling Since Boot",
            value_template=(
                "{% if value_json.throttling_occurred is defined %}"
                "{{ 'ON' if value_json.throttling_occurred else 'OFF' }}"
                "{% endif %}"
            ),
            icon="mdi:alert",
            force_update=True,
            payload_on="ON",
            payload_off="OFF",
            device_class="problem",
        ),
        _binary_sensor_component(
            hostname=hostname,
            metric="network_link",
            name="Network Link",
            value_template=(
                "{% if value_json.network_link_up is defined %}"
                "{{ 'ON' if value_json.network_link_up else 'OFF' }}"
                "{% endif %}"
            ),
            icon="mdi:ethernet",
            force_update=True,
            payload_on="ON",
            payload_off="OFF",
            device_class="connectivity",
        ),
        _binary_sensor_component(
            hostname=hostname,
            metric="reboot_required",
            name="Reboot Required",
            value_template="{{ 'ON' if value_json.reboot_required else 'OFF' }}",
            icon="mdi:restart-alert",
            force_update=False,
            payload_on="ON",
            payload_off="OFF",
            device_class="problem",
        ),
    ]

    return {component["unique_id"]: component for component in sensors}


def _fan_components(hostname: str) -> dict[str, dict[str, Any]]:
    """Build fan sensors for hosts with a Pi 5 pwmfan hwmon device."""
    sensors = [
        _sensor_component(
            hostname=hostname,
            metric="fan_speed",
            name="Fan Speed",
            value_template="{{ value_json.fan_speed_rpm }}",
            icon="mdi:fan",
            force_update=True,
            unit_of_measurement="RPM",
            state_class="measurement",
        ),
        _sensor_component(
            hostname=hostname,
            metric="fan_pwm",
            name="Fan PWM",
            value_template="{{ value_json.fan_pwm_percent }}",
            icon="mdi:fan-speed-1",
            force_update=True,
            unit_of_measurement="%",
            state_class="measurement",
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
        # Escape backslashes and single quotes in the Jinja string literal.
        jinja_path = path.replace("\\", "\\\\").replace("'", "\\'")
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


def _mount_components(
    hostname: str,
    mount_checks: Sequence[MountCheck],
) -> dict[str, dict[str, Any]]:
    """Build one problem binary sensor per configured mount check."""
    components: dict[str, dict[str, Any]] = {}
    for check in mount_checks:
        metric = f"mount_{check.identifier}_problem"
        jinja_identifier = check.identifier.replace("\\", "\\\\").replace("'", "\\'")
        health_path = f"value_json.mount_health['{jinja_identifier}']"
        component = _binary_sensor_component(
            hostname=hostname,
            metric=metric,
            name=f"Mount {check.identifier.replace('_', ' ').title()} Problem",
            value_template=(
                f"{{% if {health_path} is defined %}}"
                f"{{{{ 'OFF' if {health_path}.healthy else 'ON' }}}}"
                "{% endif %}"
            ),
            icon="mdi:harddisk-alert",
            force_update=True,
            payload_on="ON",
            payload_off="OFF",
            device_class="problem",
            entity_category="diagnostic",
        )
        component["json_attributes_template"] = f"{{{{ {health_path} | tojson }}}}"
        components[component["unique_id"]] = component
    return components


def _smart_components(
    hostname: str,
    devices: Sequence[SmartDevice],
) -> dict[str, dict[str, Any]]:
    """Build SMART health/temperature/wear sensors for detected disks."""
    components: dict[str, dict[str, Any]] = {}

    for device in devices:
        jinja_slug = device.slug.replace("\\", "\\\\").replace("'", "\\'")
        smart_path = f"value_json.smart['{jinja_slug}']"
        label = device.label

        health_metric = f"smart_{device.slug}_health"
        components[f"{hostname}_{health_metric}"] = _binary_sensor_component(
            hostname=hostname,
            metric=health_metric,
            name=f"SMART Health ({label})",
            value_template=f"{{{{ {smart_path}.health }}}}",
            icon="mdi:harddisk-plus",
            force_update=True,
            payload_on="FAILED",
            payload_off="PASSED",
            device_class="problem",
        )

        temperature_metric = f"smart_{device.slug}_temperature"
        components[f"{hostname}_{temperature_metric}"] = _sensor_component(
            hostname=hostname,
            metric=temperature_metric,
            name=f"SMART Temperature ({label})",
            value_template=f"{{{{ {smart_path}.temperature }}}}",
            icon="mdi:thermometer",
            force_update=True,
            unit_of_measurement="°C",
            state_class="measurement",
            device_class="temperature",
        )

        if device.kind == "nvme":
            wear_metric = f"smart_{device.slug}_percentage_used"
            components[f"{hostname}_{wear_metric}"] = _sensor_component(
                hostname=hostname,
                metric=wear_metric,
                name=f"SSD Wear ({label})",
                value_template=f"{{{{ {smart_path}.percentage_used }}}}",
                icon="mdi:battery-heart-variant",
                force_update=True,
                unit_of_measurement="%",
                state_class="measurement",
            )
        else:
            wear_metric = f"smart_{device.slug}_reallocated_sectors"
            components[f"{hostname}_{wear_metric}"] = _sensor_component(
                hostname=hostname,
                metric=wear_metric,
                name=f"Reallocated Sectors ({label})",
                value_template=f"{{{{ {smart_path}.reallocated_sectors }}}}",
                icon="mdi:harddisk-remove",
                force_update=True,
                state_class="measurement",
            )

    return components


def build_discovery_payload(
    hostname: str,
    disk_paths: tuple[str, ...] | list[str],
    *,
    mount_checks: Sequence[MountCheck] = (),
    has_fan: bool = False,
    smart_devices: Sequence[SmartDevice] = (),
    sw_version: str = __version__,
) -> dict[str, Any]:
    """Build a retained MQTT device-discovery payload for pi_stats.

    Args:
        hostname: Pi hostname used in topics and unique IDs.
        disk_paths: Filesystem paths that appear under `disk_usage` in the state
            payload.
        mount_checks: Explicit source/read-write/directory checks to expose.
        has_fan: When True, include pwmfan RPM/PWM sensors.
        smart_devices: SMART-capable disks to expose as optional sensors.
        sw_version: Software version advertised in the discovery origin/device.

    Returns:
        dict[str, Any]: discovery payload ready to JSON-serialize.
    """
    components = _fixed_components(hostname)
    components.update(_disk_components(hostname, disk_paths))
    components.update(_mount_components(hostname, mount_checks))
    if has_fan:
        components.update(_fan_components(hostname))
    if smart_devices:
        components.update(_smart_components(hostname, smart_devices))

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


def build_discovery_updates(
    hostname: str,
    disk_paths: tuple[str, ...] | list[str],
    previous_component_ids: set[str] | frozenset[str] | dict[str, str],
    *,
    mount_checks: Sequence[MountCheck] = (),
    has_fan: bool = False,
    smart_devices: Sequence[SmartDevice] = (),
    sw_version: str = __version__,
) -> tuple[dict[str, Any], ...]:
    """Build the ordered discovery payloads needed to update a device.

    Home Assistant requires removed device-discovery components to be published
    once as a tombstone containing only their platform before they are omitted
    from the clean payload.

    Args:
        hostname: Pi hostname used in topics and unique IDs.
        disk_paths: Currently configured filesystem paths.
        previous_component_ids: Component IDs (or ID -> platform map) published by
            the previous run.
        mount_checks: Explicit source/read-write/directory checks to expose.
        has_fan: When True, include pwmfan RPM/PWM sensors.
        smart_devices: SMART-capable disks to expose as optional sensors.
        sw_version: Software version advertised in the discovery origin/device.

    Returns:
        tuple[dict[str, Any], ...]: A tombstone payload followed by the clean
            payload when components were removed, otherwise only the clean payload.
    """
    clean_payload = build_discovery_payload(
        hostname,
        disk_paths,
        mount_checks=mount_checks,
        has_fan=has_fan,
        smart_devices=smart_devices,
        sw_version=sw_version,
    )
    current_component_ids = set(clean_payload["cmps"])
    if isinstance(previous_component_ids, dict):
        previous_platforms = previous_component_ids
        previous_ids = set(previous_platforms)
    else:
        previous_ids = set(previous_component_ids)
        previous_platforms = dict.fromkeys(previous_ids, "sensor")

    removed_component_ids = previous_ids - current_component_ids

    if not removed_component_ids:
        return (clean_payload,)

    tombstone_payload = {
        **clean_payload,
        "cmps": {
            **clean_payload["cmps"],
            **{
                component_id: {
                    "p": previous_platforms.get(component_id, "sensor"),
                }
                for component_id in sorted(removed_component_ids)
            },
        },
    }
    return tombstone_payload, clean_payload


def load_component_ids(path: Path) -> set[str]:
    """Load the component IDs from a previous successful discovery publication.

    Invalid or missing state is treated as no previous publication.
    """
    return set(load_component_platforms(path))


def load_component_platforms(path: Path) -> dict[str, str]:
    """Load component ID -> MQTT platform from a previous discovery publication.

    Supports the legacy list-of-IDs format (assumed ``sensor``) and the current
    object map of ID to platform. Invalid or missing state is treated as empty.
    """
    try:
        value = loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError, JSONDecodeError, OSError:
        return {}

    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return dict.fromkeys(value, "sensor")

    if isinstance(value, dict) and all(
        isinstance(key, str) and isinstance(platform, str)
        for key, platform in value.items()
    ):
        return dict(value)

    return {}


def save_component_ids(path: Path, component_ids: set[str]) -> None:
    """Atomically persist component IDs as sensors (legacy helper)."""
    save_component_platforms(path, dict.fromkeys(sorted(component_ids), "sensor"))


def save_component_platforms(path: Path, component_platforms: dict[str, str]) -> None:
    """Atomically persist component ID -> MQTT platform from a discovery publication."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(
        dumps(dict(sorted(component_platforms.items()))),
        encoding="utf-8",
    )
    temporary_path.replace(path)
