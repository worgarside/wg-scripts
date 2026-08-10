"""This script sends system stats to HA for use in system health stuff."""

from __future__ import annotations

import re
import socket
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from json import JSONDecodeError, dumps, loads
from os import getenv, getloadavg
from pathlib import Path
from subprocess import run  # noqa: S404
from threading import Event
from time import monotonic, sleep, time
from typing import TYPE_CHECKING, ClassVar, Final, NotRequired, TypedDict

import psutil
from wg_utilities.decorators import process_exception
from wg_utilities.functions import run_cmd
from wg_utilities.loggers import get_streaming_logger
from wg_utilities.utils import mqtt

from services.pi_stats.discovery import (
    PAYLOAD_OFFLINE,
    PAYLOAD_ONLINE,
    SmartDevice,
    SmartKind,
    availability_topic,
    build_discovery_updates,
    discovery_topic,
    disk_path_slugs,
    load_component_platforms,
    path_to_slug,
    save_component_platforms,
    stats_topic,
)
from services.pi_stats.mount_health import (
    MountHealth,
    collect_mount_health,
    parse_mount_checks,
)
from wg_scripts import __version__

if TYPE_CHECKING:
    from paho.mqtt.client import Client, ConnectFlags, MQTTMessageInfo
    from paho.mqtt.properties import Properties
    from paho.mqtt.reasoncodes import ReasonCode

LOGGER = get_streaming_logger(__name__)

# =============================================================================
# Constants

IP_FALLBACK: Final = f"{mqtt.HOSTNAME}.local"
ONE_MINUTE: Final = 60
HWMON_ROOT: Final = Path("/sys/class/hwmon")
PWM_MAX_DUTY: Final = 255
SMARTCTL: Final = "/usr/sbin/smartctl"
APT_BIN: Final = "/usr/bin/apt"
REBOOT_REQUIRED_PATH: Final = Path("/var/run/reboot-required")
THROTTLED_ACTIVE_MASK: Final = 0xF
THROTTLED_OCCURRED_MASK: Final = 0xF0000
THROTTLED_OUTPUT: Final = re.compile(r"throttled=(0x[0-9a-fA-F]+)")
VIRTUAL_INTERFACE_PREFIXES: Final = (
    "lo",
    "docker",
    "br-",
    "veth",
    "virbr",
    "tailscale",
    "wg",
)
ATA_WEAR_ATTRIBUTE_IDS: Final = frozenset({5, 197})
# Prefer sat first: common for USB-SATA bridges that smartctl --scan-open skips
# (e.g. JMicron 0x152d:0xa578 on vaultpi).
SMART_TRANSPORT_FALLBACKS: Final = (
    "sat",
    "sat,12",
    "sat,16",
    "scsi",
    "usbjmicron",
    "auto",
)
NVME_NAMESPACE: Final = re.compile(r"^(nvme\d+)n\d+$")

SERVICE_START_TIME: Final = datetime.now(UTC).isoformat()

DISK_USAGE_PATHS: Final[tuple[str, ...]] = tuple(
    path.strip()
    for path in getenv("DISK_USAGE_PATHS", "/home").split(",")
    if path.strip()
)
MOUNT_CHECKS: Final = parse_mount_checks(getenv("PI_STATS_MOUNTS_JSON", "[]"))


def _positive_int_env(name: str, default: str) -> int:
    """Parse a positive integer environment variable or raise ValueError."""
    raw = getenv(name, default)
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer, got {raw!r}") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer, got {value}")
    return value


APT_CHECK_INTERVAL_SECONDS: Final = _positive_int_env(
    "APT_CHECK_INTERVAL_SECONDS",
    "21600",
)
MQTT_DISCONNECT_EXIT_SECONDS: Final = _positive_int_env(
    "PI_STATS_MQTT_DISCONNECT_EXIT_SECONDS",
    "60",
)

AVAILABILITY_TOPIC: Final = availability_topic(mqtt.HOSTNAME)
DISCOVERY_TOPIC: Final = discovery_topic(mqtt.HOSTNAME)
DISCOVERY_STATE_PATH: Final = Path(
    getenv(
        "PI_STATS_DISCOVERY_STATE_PATH",
        str(Path.home() / ".cache/wg-scripts/pi_stats-discovery-components.json"),
    ),
)
PUBLISH_TIMEOUT_SECONDS: Final = 5

# Set from on_connect; consumed on the main thread so wait_for_publish cannot deadlock
# the Paho network loop.
_DISCOVERY_NEEDED: Final = Event()
_FAN_READ_ERRORS_LOGGED: Final[set[str]] = set()
_SMART_READ_ERRORS_LOGGED: Final[set[str]] = set()
_APT_READ_ERRORS_LOGGED: Final[set[str]] = set()
_THROTTLED_READ_ERRORS_LOGGED: Final[set[str]] = set()


class SmartDeviceStats(TypedDict):
    """Per-disk SMART sample included under ``Stats.smart``."""

    health: str
    temperature: NotRequired[float]
    reallocated_sectors: NotRequired[int]
    percentage_used: NotRequired[int]


class Stats(TypedDict):
    """Type definition for the stats dictionary."""

    cpu_usage: float
    memory_usage: float
    temperature: float
    disk_usage: dict[str, float]
    mount_health: NotRequired[dict[str, MountHealth]]
    load_1m: float
    load_5m: float
    load_15m: float
    uptime: int
    boot_time: str
    local_git_ref: str
    active_git_ref: str
    local_ip: str
    service_start_time: str
    wg_scripts_version: str
    fan_speed_rpm: NotRequired[int]
    fan_pwm_percent: NotRequired[float]
    smart: NotRequired[dict[str, SmartDeviceStats]]
    throttled_flags: NotRequired[int]
    throttling_active: NotRequired[bool]
    throttling_occurred: NotRequired[bool]
    cpu_frequency_mhz: NotRequired[float]
    swap_usage: float
    cpu_iowait: float
    network_interface: NotRequired[str]
    network_link_up: NotRequired[bool]
    network_receive_bytes_per_second: NotRequired[float]
    network_transmit_bytes_per_second: NotRequired[float]
    pending_updates: NotRequired[int]
    reboot_required: bool


@dataclass(frozen=True, slots=True)
class PwmFanHwmon:
    """Sysfs paths for a detected Pi 5 pwmfan hwmon device."""

    fan_input: Path
    pwm: Path


@lru_cache(maxsize=1)
def find_pwmfan_hwmon() -> PwmFanHwmon | None:
    """Locate the Pi 5 Active Cooler pwmfan hwmon device, if present."""
    if not HWMON_ROOT.is_dir():
        return None

    for hwmon in sorted(HWMON_ROOT.glob("hwmon*")):
        try:
            name = (hwmon / "name").read_text(encoding="utf-8").strip()
        except OSError:
            continue

        if name != "pwmfan":
            continue

        fan_input = hwmon / "fan1_input"
        pwm = hwmon / "pwm1"
        if fan_input.is_file() and pwm.is_file():
            LOGGER.info("Detected pwmfan hwmon at %s", hwmon)
            return PwmFanHwmon(fan_input=fan_input, pwm=pwm)

    return None


def read_fan_stats() -> tuple[int, float] | None:
    """Read fan RPM and PWM duty percent from pwmfan, if available.

    Returns:
        tuple[int, float] | None: ``(rpm, pwm_percent)`` when readable, otherwise
        ``None`` (no pwmfan, or a read failure for this sample).
    """
    hwmon = find_pwmfan_hwmon()
    if hwmon is None:
        return None

    try:
        rpm = int(hwmon.fan_input.read_text(encoding="utf-8").strip())
        pwm_raw = int(hwmon.pwm.read_text(encoding="utf-8").strip())
    except (OSError, ValueError) as exc:
        error_key = type(exc).__name__
        if error_key not in _FAN_READ_ERRORS_LOGGED:
            _FAN_READ_ERRORS_LOGGED.add(error_key)
            LOGGER.exception("Failed to read pwmfan stats")
        return None

    return rpm, float(round(pwm_raw / PWM_MAX_DUTY * 100, 1))


def _run_smartctl(*args: str) -> dict[str, object] | None:
    """Run ``sudo -n smartctl`` with JSON output, returning parsed stdout.

    ``smartctl`` uses a bitmask exit status even on successful reads, so non-zero
    exits are ignored when valid JSON is returned. Missing binary, sudo denial,
    or unparsable output all yield ``None`` without treating the exit code as fatal.
    """
    cmd = ["sudo", "-n", SMARTCTL, *args]
    try:
        completed = run(  # noqa: S603
            cmd,
            capture_output=True,
            check=False,
            text=True,
        )
    except FileNotFoundError, PermissionError:
        LOGGER.debug("smartctl unavailable (%s)", SMARTCTL)
        return None
    except OSError:
        LOGGER.exception("Failed to invoke smartctl")
        return None

    output = completed.stdout.strip()
    if not output:
        error = completed.stderr.strip()
        if error:
            LOGGER.debug("smartctl produced no output: %s", error)
        return None

    try:
        payload = loads(output)
    except JSONDecodeError:
        LOGGER.debug("smartctl returned non-JSON output: %s", output[:200])
        return None

    if not isinstance(payload, dict):
        return None

    return payload


def _smart_kind(device: str, transport: str, probe: dict[str, object]) -> SmartKind:
    """Classify a SMART device as ATA or NVMe from probe data / transport."""
    if "nvme_smart_health_information_log" in probe:
        return "nvme"
    if "ata_smart_attributes" in probe:
        return "ata"
    if "nvme" in transport.casefold() or "nvme" in device.casefold():
        return "nvme"
    return "ata"


def _block_device_candidates() -> tuple[str, ...]:
    """Return whole-disk device nodes that may support SMART.

    Skips loop/zram/ram/dm/md and mmc (SD/eMMC). NVMe namespaces are mapped to
    the controller node (``/dev/nvme0n1`` → ``/dev/nvme0``) to match smartctl
    ``--scan-open``.
    """
    sys_block = Path("/sys/block")
    if not sys_block.is_dir():
        return ()

    devices: list[str] = []
    seen: set[str] = set()

    for entry in sorted(sys_block.iterdir()):
        name = entry.name
        if name.startswith(("loop", "ram", "zram", "dm-", "md", "mmcblk")):
            continue

        nvme_match = NVME_NAMESPACE.fullmatch(name)
        device = f"/dev/{nvme_match.group(1)}" if nvme_match else f"/dev/{name}"
        if device in seen or not Path(device).exists():
            continue
        seen.add(device)
        devices.append(device)

    return tuple(devices)


def _probe_smart_device(
    name: str,
    preferred_transport: str | None = None,
) -> tuple[str, dict[str, object]] | None:
    """Probe a device with preferred then fallback transports until SMART answers.

    Uses ``-i -H`` so identity (model name) is available alongside health.
    """
    transports: list[str] = []
    if preferred_transport:
        transports.append(preferred_transport)
    if "nvme" in name.casefold():
        transports.append("nvme")
    else:
        transports.extend(SMART_TRANSPORT_FALLBACKS)

    tried: set[str] = set()
    for transport in transports:
        if transport in tried:
            continue
        tried.add(transport)
        probe = _run_smartctl("-d", transport, "-i", "-H", "-j", name)
        if probe is not None and "smart_status" in probe:
            return transport, probe

    return None


def _smart_label(probe: dict[str, object], device: str) -> str:
    """Best-effort friendly disk name from smartctl identity fields."""
    for key in ("model_name", "scsi_model_name"):
        value = probe.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return device


def _disambiguate_smart_labels(devices: list[SmartDevice]) -> list[SmartDevice]:
    """Append the device basename when multiple disks share a model label."""
    label_counts: dict[str, int] = {}
    for device in devices:
        label_counts[device.label] = label_counts.get(device.label, 0) + 1

    if all(count == 1 for count in label_counts.values()):
        return devices

    return [
        SmartDevice(
            device=device.device,
            transport=device.transport,
            kind=device.kind,
            slug=device.slug,
            label=(
                device.label
                if label_counts[device.label] == 1
                else f"{device.label} ({Path(device.device).name})"
            ),
        )
        for device in devices
    ]


def _scan_open_candidates() -> list[tuple[str, str | None]] | None:
    """Return ``(device, transport)`` pairs from ``smartctl --scan-open``.

    Returns ``None`` when smartctl cannot be invoked; an empty list when it can
    but found no devices.
    """
    scan = _run_smartctl("--scan-open", "-j")
    if scan is None:
        return None

    candidates: list[tuple[str, str | None]] = []
    seen_names: set[str] = set()
    raw_devices = scan.get("devices")
    if not isinstance(raw_devices, list):
        return candidates

    for entry in raw_devices:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        transport = entry.get("type")
        if not isinstance(name, str) or not isinstance(transport, str):
            continue
        if name in seen_names:
            continue
        seen_names.add(name)
        candidates.append((name, transport))

    return candidates


def _smart_candidates() -> list[tuple[str, str | None]] | None:
    """Merge scan-open and ``/sys/block`` candidates.

    Returns ``None`` when smartctl cannot be invoked at all.
    """
    scan_candidates = _scan_open_candidates()
    if scan_candidates is None:
        return None

    candidates = list(scan_candidates)
    seen_names = {name for name, _transport in candidates}
    for name in _block_device_candidates():
        if name in seen_names:
            continue
        seen_names.add(name)
        candidates.append((name, None))

    return candidates


@lru_cache(maxsize=1)
def find_smart_devices() -> tuple[SmartDevice, ...]:
    """Detect SMART-capable disks via scan-open plus block-device fallbacks.

    ``smartctl --scan-open`` misses some USB-SATA bridges (unknown VID:PID). For
    those, whole disks from ``/sys/block`` are probed with ``-d sat`` and other
    common transports. Returns an empty tuple when smartctl is missing, sudo is
    denied, or nothing answers a health probe (e.g. SD-only Pis).
    """
    candidates = _smart_candidates()
    if candidates is None:
        return ()

    detected: list[SmartDevice] = []
    seen_slugs: set[str] = set()

    for name, preferred_transport in candidates:
        probed = _probe_smart_device(name, preferred_transport)
        if probed is None:
            continue

        transport, probe = probed
        kind = _smart_kind(name, transport, probe)
        slug = path_to_slug(name)
        if slug in seen_slugs:
            LOGGER.warning(
                "Skipping SMART device %s due to slug collision on %r",
                name,
                slug,
            )
            continue

        seen_slugs.add(slug)
        detected.append(
            SmartDevice(
                device=name,
                transport=transport,
                kind=kind,
                slug=slug,
                label=_smart_label(probe, name),
            ),
        )

    detected = _disambiguate_smart_labels(detected)

    if detected:
        LOGGER.info(
            "Detected SMART devices: %s",
            ", ".join(
                f"{device.label} [{device.device} {device.kind}/{device.transport}]"
                for device in detected
            ),
        )

    return tuple(detected)


def _ata_wear_sectors(probe: dict[str, object]) -> int | None:
    """Return max(reallocated, pending) from ATA attributes 5 and 197."""
    attributes = probe.get("ata_smart_attributes")
    if not isinstance(attributes, dict):
        return None

    table = attributes.get("table")
    if not isinstance(table, list):
        return None

    candidates: list[int] = []
    for row in table:
        if not isinstance(row, dict):
            continue
        attr_id = row.get("id")
        if attr_id not in ATA_WEAR_ATTRIBUTE_IDS:
            continue
        raw = row.get("raw")
        if not isinstance(raw, dict):
            continue
        value = raw.get("value")
        if isinstance(value, bool) or not isinstance(value, int):
            continue
        candidates.append(value)

    return max(candidates) if candidates else None


def _as_float(value: object) -> float | None:
    """Coerce a JSON number to float, rejecting bools."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _as_int(value: object) -> int | None:
    """Coerce a JSON number to int, rejecting bools."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _probe_temperature(probe: dict[str, object]) -> float | None:
    """Read ``temperature.current`` from a smartctl JSON probe."""
    temperature = probe.get("temperature")
    if not isinstance(temperature, dict):
        return None
    return _as_float(temperature.get("current"))


def _nvme_percentage_used(probe: dict[str, object]) -> int | None:
    """Read NVMe ``percentage_used`` from a smartctl JSON probe."""
    nvme_log = probe.get("nvme_smart_health_information_log")
    if not isinstance(nvme_log, dict):
        return None
    return _as_int(nvme_log.get("percentage_used"))


def _parse_smart_device_stats(
    device: SmartDevice,
    probe: dict[str, object],
) -> SmartDeviceStats | None:
    """Extract the curated SMART fields for one device sample."""
    smart_status = probe.get("smart_status")
    if not isinstance(smart_status, dict) or "passed" not in smart_status:
        return None

    passed = smart_status.get("passed")
    if not isinstance(passed, bool):
        return None

    stats: SmartDeviceStats = {
        "health": "PASSED" if passed else "FAILED",
    }

    if (temperature := _probe_temperature(probe)) is not None:
        stats["temperature"] = temperature

    if device.kind == "nvme":
        if (percentage_used := _nvme_percentage_used(probe)) is not None:
            stats["percentage_used"] = percentage_used
    elif (wear := _ata_wear_sectors(probe)) is not None:
        stats["reallocated_sectors"] = wear

    return stats


def read_smart_stats(
    devices: tuple[SmartDevice, ...] | None = None,
) -> dict[str, SmartDeviceStats]:
    """Read curated SMART stats for each detected (or provided) device.

    Devices that fail for a sample are omitted; the first failure of each type is
    logged, matching the pwmfan error-dedupe pattern.
    """
    targets = find_smart_devices() if devices is None else devices
    results: dict[str, SmartDeviceStats] = {}

    for device in targets:
        try:
            probe = _run_smartctl(
                "-d",
                device.transport,
                "-A",
                "-H",
                "-j",
                device.device,
            )
        except Exception as exc:
            error_key = f"{device.device}:{type(exc).__name__}"
            if error_key not in _SMART_READ_ERRORS_LOGGED:
                _SMART_READ_ERRORS_LOGGED.add(error_key)
                LOGGER.exception("Failed to read SMART stats for %s", device.device)
            continue

        if probe is None:
            error_key = f"{device.device}:NoOutput"
            if error_key not in _SMART_READ_ERRORS_LOGGED:
                _SMART_READ_ERRORS_LOGGED.add(error_key)
                LOGGER.warning(
                    "SMART read for %s returned no usable JSON", device.device
                )
            continue

        parsed = _parse_smart_device_stats(device, probe)
        if parsed is None:
            error_key = f"{device.device}:MissingStatus"
            if error_key not in _SMART_READ_ERRORS_LOGGED:
                _SMART_READ_ERRORS_LOGGED.add(error_key)
                LOGGER.warning(
                    "SMART probe for %s missing smart_status.passed",
                    device.device,
                )
            continue

        results[device.slug] = parsed

    return results


@lru_cache(maxsize=1)
def local_git_ref() -> str:
    """Get the current git ref for the local repo."""
    output, error = run_cmd("git describe --tags --exact-match", exit_on_error=False)

    if "no tag exactly matches" in error:
        output, _ = run_cmd("git rev-parse --short HEAD")

    return output.strip()


@lru_cache(maxsize=1)
def local_ip() -> str:
    """Get the local IP address of the Pi.

    https://stackoverflow.com/a/28950776/7689800
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)

    ip = IP_FALLBACK

    try:
        s.connect(("10.254.254.254", 1))
        ip = s.getsockname()[0]
    except Exception:
        LOGGER.exception("Failed to get local IP address")
    finally:
        s.close()

    return str(ip)


def read_throttled_flags() -> tuple[int, bool, bool] | None:
    """Read and decode ``vcgencmd get_throttled``.

    Returns:
        ``(flags, active, occurred)`` when readable, otherwise ``None``.
        ``active`` covers bits 0-3; ``occurred`` covers sticky bits 16-19.
    """
    try:
        output, error = run_cmd("vcgencmd get_throttled", exit_on_error=False)
    except OSError as exc:
        error_key = type(exc).__name__
        if error_key not in _THROTTLED_READ_ERRORS_LOGGED:
            _THROTTLED_READ_ERRORS_LOGGED.add(error_key)
            LOGGER.exception("Failed to read vcgencmd get_throttled")
        return None

    match = THROTTLED_OUTPUT.search(output)
    if match is None:
        error_key = "ParseError"
        if error_key not in _THROTTLED_READ_ERRORS_LOGGED:
            _THROTTLED_READ_ERRORS_LOGGED.add(error_key)
            LOGGER.warning(
                "Unexpected get_throttled output: %r (stderr=%r)",
                output,
                error,
            )
        return None

    flags = int(match.group(1), 16)
    return (
        flags,
        bool(flags & THROTTLED_ACTIVE_MASK),
        bool(flags & THROTTLED_OCCURRED_MASK),
    )


def read_cpu_frequency_mhz() -> float | None:
    """Return current CPU frequency in MHz, if available."""
    try:
        freq = psutil.cpu_freq()
    except OSError:
        return None
    if freq.current <= 0:
        return None
    return float(round(freq.current, 1))


def read_cpu_iowait_percent() -> float:
    """Return non-blocking CPU iowait percentage for this sample."""
    cpu_times = psutil.cpu_times_percent(interval=None)
    return float(round(getattr(cpu_times, "iowait", 0.0), 2))


class NetworkSample(TypedDict):
    """Primary-interface network fields for one stats sample."""

    network_interface: NotRequired[str]
    network_link_up: NotRequired[bool]
    network_receive_bytes_per_second: NotRequired[float]
    network_transmit_bytes_per_second: NotRequired[float]


def is_virtual_interface(name: str) -> bool:
    """Return True for loopback / container / VPN virtual interfaces."""
    return name.startswith(VIRTUAL_INTERFACE_PREFIXES)


def select_primary_interface(ip_address: str) -> str | None:
    """Pick the interface owning ``ip_address``, else first up physical NIC."""
    try:
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
    except OSError:
        LOGGER.exception("Failed to enumerate network interfaces")
        return None

    for name, addresses in addrs.items():
        if is_virtual_interface(name):
            continue
        for address in addresses:
            if address.family == socket.AF_INET and address.address == ip_address:
                return name

    for name, nic_stats in stats.items():
        if is_virtual_interface(name) or not nic_stats.isup:
            continue
        return name

    return None


def count_pending_updates() -> int | None:
    """Count packages reported by ``apt list --upgradable`` (no index refresh)."""
    try:
        completed = run(  # noqa: S603
            [APT_BIN, "list", "--upgradable"],
            capture_output=True,
            check=False,
            text=True,
        )
    except FileNotFoundError, PermissionError:
        error_key = "Unavailable"
        if error_key not in _APT_READ_ERRORS_LOGGED:
            _APT_READ_ERRORS_LOGGED.add(error_key)
            LOGGER.warning("apt unavailable at %s", APT_BIN)
        return None
    except OSError as exc:
        error_key = type(exc).__name__
        if error_key not in _APT_READ_ERRORS_LOGGED:
            _APT_READ_ERRORS_LOGGED.add(error_key)
            LOGGER.exception("Failed to invoke apt list --upgradable")
        return None

    if completed.returncode != 0 and not completed.stdout.strip():
        error_key = f"Exit{completed.returncode}"
        if error_key not in _APT_READ_ERRORS_LOGGED:
            _APT_READ_ERRORS_LOGGED.add(error_key)
            LOGGER.warning(
                "apt list --upgradable failed: %s",
                completed.stderr.strip() or completed.returncode,
            )
        return None

    count = 0
    for line in completed.stdout.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("Listing"):
            continue
        count += 1
    return count


def reboot_required() -> bool:
    """Return whether the host has a pending reboot marker."""
    return REBOOT_REQUIRED_PATH.exists()


@dataclass
class RaspberryPi:
    """Class to represent a Pi and its current statistics."""

    ACTIVE_GIT_REF: ClassVar[str] = local_git_ref()

    STATS_TOPIC: ClassVar[str] = stats_topic(mqtt.HOSTNAME)

    boot_time: float = field(default_factory=psutil.boot_time)
    boot_time_iso: str = field(init=False)

    get_count: int = 0
    smart_cache: dict[str, SmartDeviceStats] = field(default_factory=dict)
    pending_updates: int | None = None
    pending_updates_checked_at: float = 0.0
    net_sample_mono: float | None = None
    net_bytes_recv: int | None = None
    net_bytes_sent: int | None = None

    def __post_init__(self) -> None:
        """Prime non-blocking CPU percent counters before the first sample."""
        psutil.cpu_percent(interval=None)
        psutil.cpu_times_percent(interval=None)
        self.boot_time_iso = datetime.fromtimestamp(self.boot_time, tz=UTC).isoformat()
        self._refresh_pending_updates(force=True)

    def _refresh_pending_updates(self, *, force: bool = False) -> None:
        """Refresh the cached apt upgradable count on the configured cadence."""
        now = monotonic()
        if (
            not force
            and self.pending_updates is not None
            and (now - self.pending_updates_checked_at) < APT_CHECK_INTERVAL_SECONDS
        ):
            return

        counted = count_pending_updates()
        self.pending_updates_checked_at = now
        if counted is not None:
            self.pending_updates = counted

    def _network_stats(self, ip_address: str) -> NetworkSample:
        """Collect primary-interface link state and byte rates."""
        result: NetworkSample = {}
        interface = select_primary_interface(ip_address)
        if interface is None:
            return result

        result["network_interface"] = interface

        try:
            nic_stats = psutil.net_if_stats().get(interface)
            counters = psutil.net_io_counters(pernic=True).get(interface)
        except OSError:
            LOGGER.exception("Failed to read network stats for %s", interface)
            return result

        if nic_stats is not None:
            result["network_link_up"] = bool(nic_stats.isup)

        now = monotonic()
        if counters is not None:
            if (
                self.net_sample_mono is not None
                and self.net_bytes_recv is not None
                and self.net_bytes_sent is not None
            ):
                elapsed = now - self.net_sample_mono
                if elapsed > 0:
                    result["network_receive_bytes_per_second"] = float(
                        round((counters.bytes_recv - self.net_bytes_recv) / elapsed, 1),
                    )
                    result["network_transmit_bytes_per_second"] = float(
                        round((counters.bytes_sent - self.net_bytes_sent) / elapsed, 1),
                    )

            self.net_sample_mono = now
            self.net_bytes_recv = int(counters.bytes_recv)
            self.net_bytes_sent = int(counters.bytes_sent)

        return result

    def _attach_network_stats(self, stats: Stats) -> None:
        """Attach primary-interface network fields onto a stats payload."""
        network = self._network_stats(stats["local_ip"])
        if "network_interface" in network:
            stats["network_interface"] = network["network_interface"]
        if "network_link_up" in network:
            stats["network_link_up"] = network["network_link_up"]
        if "network_receive_bytes_per_second" in network:
            stats["network_receive_bytes_per_second"] = network[
                "network_receive_bytes_per_second"
            ]
        if "network_transmit_bytes_per_second" in network:
            stats["network_transmit_bytes_per_second"] = network[
                "network_transmit_bytes_per_second"
            ]

    def _attach_optional_stats(self, stats: Stats, *, refresh_slow: bool) -> None:
        """Attach optional / cached fields onto a base stats payload."""
        if (fan_stats := read_fan_stats()) is not None:
            fan_speed_rpm, fan_pwm_percent = fan_stats
            stats["fan_speed_rpm"] = fan_speed_rpm
            stats["fan_pwm_percent"] = fan_pwm_percent

        smart_devices = find_smart_devices()
        if smart_devices:
            if refresh_slow or not self.smart_cache:
                self.smart_cache = read_smart_stats(smart_devices)
            stats["smart"] = self.smart_cache

        if (throttled := read_throttled_flags()) is not None:
            flags, active, occurred = throttled
            stats["throttled_flags"] = flags
            stats["throttling_active"] = active
            stats["throttling_occurred"] = occurred

        if (cpu_frequency_mhz := read_cpu_frequency_mhz()) is not None:
            stats["cpu_frequency_mhz"] = cpu_frequency_mhz

        self._attach_network_stats(stats)

        if self.pending_updates is not None:
            stats["pending_updates"] = self.pending_updates

    def get_stats(self) -> Stats:
        """Get the current stats for the Pi.

        Returns:
            Stats: the current stats for the Pi.
        """
        # Doing this first and separately so the other properties don't affect the
        # readings
        load_1m, load_5m, load_15m = self.load_averages
        cpu_iowait = read_cpu_iowait_percent()

        cpu_usage, memory_usage, temperature, uptime = (
            self.cpu_usage,
            self.memory_usage,
            self.cpu_temp,
            self.uptime,
        )

        refresh_slow = self.get_count % 5 == 0
        if refresh_slow:
            local_git_ref.cache_clear()
            local_ip.cache_clear()

            self.boot_time = psutil.boot_time()
            self.boot_time_iso = datetime.fromtimestamp(
                self.boot_time,
                tz=UTC,
            ).isoformat()
        elif local_ip() == IP_FALLBACK:
            local_ip.cache_clear()

        self.get_count += 1
        self._refresh_pending_updates()

        stats: Stats = {
            "cpu_usage": cpu_usage,
            "memory_usage": memory_usage,
            "temperature": temperature,
            "disk_usage": self.disk_usage,
            "load_1m": load_1m,
            "load_5m": load_5m,
            "load_15m": load_15m,
            "uptime": uptime,
            "boot_time": self.boot_time_iso,
            "local_git_ref": local_git_ref(),
            "active_git_ref": self.ACTIVE_GIT_REF,
            "local_ip": local_ip(),
            "service_start_time": SERVICE_START_TIME,
            "wg_scripts_version": __version__,
            "swap_usage": float(round(psutil.swap_memory().percent, 2)),
            "cpu_iowait": cpu_iowait,
            "reboot_required": reboot_required(),
        }
        if MOUNT_CHECKS:
            stats["mount_health"] = collect_mount_health(MOUNT_CHECKS)
        self._attach_optional_stats(stats, refresh_slow=refresh_slow)
        return stats

    @property
    def cpu_temp(self) -> float:
        """Get the current CPU temperature.

        Returns:
            float: the current CPU temperature in Celsius.
        """
        output, _ = run_cmd("vcgencmd measure_temp")
        return float(output.replace("temp=", "").replace("'C", ""))

    @property
    def disk_usage(self) -> dict[str, float]:
        """Get the current disk usage percentage for each configured path.

        Returns:
            dict[str, float]: path to usage percentage mapping. Unavailable paths
            are omitted for this sample.
        """
        usage: dict[str, float] = {}

        for path in DISK_USAGE_PATHS:
            try:
                usage[path] = float(round(psutil.disk_usage(path).percent, 2))
            except OSError:
                LOGGER.exception("Failed to get disk usage for %s", path)

        return usage

    @property
    def memory_usage(self) -> float:
        """Get the current memory usage percentage.

        Returns:
            float: the percentage of memory currently in use.
        """
        return float(round(psutil.virtual_memory().percent, 2))

    @property
    def cpu_usage(self) -> float:
        """Get the current CPU usage percentage.

        Returns:
            float: the percentage of CPU currently in use.
        """
        return float(round(psutil.cpu_percent(interval=None), 2))

    @property
    def load_averages(self) -> tuple[float, float, float]:
        """Get the average system load over the last 1, 5, and 15 minutes.

        Returns:
            tuple: average recent system load information.
        """
        load_1m, load_5m, load_15m = getloadavg()
        return (
            float(round(load_1m, 2)),
            float(round(load_5m, 2)),
            float(round(load_15m, 2)),
        )

    @property
    def uptime(self) -> int:
        """Get the current uptime in seconds.

        Returns:
            int: the current uptime in seconds.
        """
        return int(time() - self.boot_time)


def publish_discovery(client: Client) -> None:
    """Publish retained MQTT device discovery, including removal tombstones.

    Must run on the main thread (not inside a Paho callback): QoS 1 acks are
    processed by the network loop, so ``wait_for_publish`` from ``on_connect``
    would deadlock.
    """
    previous_component_platforms = load_component_platforms(DISCOVERY_STATE_PATH)
    payloads = build_discovery_updates(
        mqtt.HOSTNAME,
        DISK_USAGE_PATHS,
        previous_component_platforms,
        mount_checks=MOUNT_CHECKS,
        has_fan=find_pwmfan_hwmon() is not None,
        smart_devices=find_smart_devices(),
    )

    for payload in payloads:
        message = client.publish(
            topic=DISCOVERY_TOPIC,
            payload=dumps(payload),
            retain=True,
            qos=1,
        )
        message.wait_for_publish(timeout=PUBLISH_TIMEOUT_SECONDS)
        if not message.is_published():
            raise TimeoutError(
                f"Discovery publish to {DISCOVERY_TOPIC} was not acknowledged",
            )

    clean_payload = payloads[-1]
    component_platforms = {
        component_id: str(component.get("p", "sensor"))
        for component_id, component in clean_payload["cmps"].items()
    }
    save_component_platforms(DISCOVERY_STATE_PATH, component_platforms)
    LOGGER.info(
        "Published MQTT discovery for %s (%d components, %d updates) to %s",
        mqtt.HOSTNAME,
        len(clean_payload["cmps"]),
        len(payloads),
        DISCOVERY_TOPIC,
    )


def publish_availability(client: Client, payload: str) -> MQTTMessageInfo:
    """Publish retained online/offline availability for pi_stats."""
    return client.publish(
        topic=AVAILABILITY_TOPIC,
        payload=payload,
        retain=True,
        qos=1,
    )


def on_connect(
    client: Client,
    _userdata: object,
    _connect_flags: ConnectFlags,
    reason_code: ReasonCode,
    _properties: Properties | None,
) -> None:
    """Restore availability after every successful connection; schedule discovery."""
    if reason_code.is_failure:
        LOGGER.error("MQTT connection failed: %s", reason_code)
        return

    LOGGER.info("Connected to MQTT broker")

    # Keep availability independent of discovery so a cache/publish failure cannot
    # leave entities stuck unavailable after an LWT offline.
    try:
        publish_availability(client, PAYLOAD_ONLINE)
    except Exception:
        LOGGER.exception("Failed to publish MQTT availability after connecting")

    _DISCOVERY_NEEDED.set()


def publish_discovery_if_needed(client: Client) -> None:
    """Publish discovery from the main thread when a connection requested it."""
    if not _DISCOVERY_NEEDED.is_set() or not client.is_connected():
        return

    _DISCOVERY_NEEDED.clear()
    try:
        publish_discovery(client)
    except Exception:
        LOGGER.exception("Failed to publish MQTT discovery after connecting")


def shutdown(client: Client) -> None:
    """Flush offline availability before disconnecting cleanly."""
    message = publish_availability(client, PAYLOAD_OFFLINE)
    try:
        message.wait_for_publish(timeout=PUBLISH_TIMEOUT_SECONDS)
        if message.is_published():
            client.disconnect()
        else:
            LOGGER.warning(
                "Offline availability was not acknowledged; relying on MQTT last will",
            )
    finally:
        client.loop_stop()


def record_mqtt_disconnection(disconnected_since: float | None) -> float:
    """Record a disconnection or exit after the recovery deadline expires."""
    now = monotonic()
    if disconnected_since is None:
        LOGGER.warning(
            "Disconnected from MQTT broker; waiting up to %d seconds for automatic "
            "reconnection",
            MQTT_DISCONNECT_EXIT_SECONDS,
        )
        return now

    if now - disconnected_since >= MQTT_DISCONNECT_EXIT_SECONDS:
        LOGGER.error(
            "MQTT broker remained disconnected for %d seconds; exiting so the "
            "service manager can restart the process",
            MQTT_DISCONNECT_EXIT_SECONDS,
        )
        raise SystemExit(1)

    return disconnected_since


@process_exception(logger=LOGGER)
def main() -> None:
    """Sends system stats to Home Assistant every minute."""
    # Fail fast on bad DISK_USAGE_PATHS before touching the broker.
    disk_path_slugs(DISK_USAGE_PATHS)

    rasp_pi = RaspberryPi()

    # Last will must be set before connecting so abrupt exits mark the service offline.
    mqtt.CLIENT.will_set(
        topic=AVAILABILITY_TOPIC,
        payload=PAYLOAD_OFFLINE,
        qos=1,
        retain=True,
    )
    mqtt.CLIENT.on_connect = on_connect

    mqtt.CLIENT.connect(mqtt.MQTT_HOST)
    mqtt.CLIENT.loop_start()

    for _ in range(120):
        if mqtt.CLIENT.is_connected():
            break

        LOGGER.info("Waiting for connection to MQTT broker...")
        sleep(1)

    if not mqtt.CLIENT.is_connected():
        LOGGER.error("Failed to connect to MQTT broker, exiting")
        raise SystemExit(1)

    disconnected_since: float | None = None

    try:
        # This is done as a while loop, rather than a cron job, so that instantiating
        # the pi etc. every time doesn't influence the readings
        with suppress(KeyboardInterrupt):
            while True:
                publish_discovery_if_needed(mqtt.CLIENT)

                if not mqtt.CLIENT.is_connected():
                    disconnected_since = record_mqtt_disconnection(disconnected_since)
                    sleep(1)
                    continue

                disconnected_since = None

                try:
                    mqtt.CLIENT.publish(
                        topic=rasp_pi.STATS_TOPIC,
                        payload=dumps(rasp_pi.get_stats()),
                        retain=False,
                        qos=1,
                    )
                except TimeoutError:
                    LOGGER.exception(
                        "%s timed out sending stats, exiting",
                        mqtt.HOSTNAME,
                    )
                    raise SystemExit from None

                # Chunk the interval so reconnect discovery runs promptly.
                for _ in range(ONE_MINUTE):
                    if _DISCOVERY_NEEDED.is_set() or not mqtt.CLIENT.is_connected():
                        break
                    sleep(1)
    finally:
        with suppress(Exception):
            shutdown(mqtt.CLIENT)

    LOGGER.info("Disconnected from MQTT broker, exiting")
    raise SystemExit


if __name__ == "__main__":
    main()
