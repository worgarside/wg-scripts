# Pi Stats

Reports system stats to an MQTT broker and publishes Home Assistant MQTT device
discovery so entities are created automatically.

## Environment Variables

| Name | Description | Default |
|------|-------------|---------|
| HOSTNAME | The Pi's hostname | `<hostname>` |
| MQTT_HOST | MQTT broker host | `homeassistant.local` |
| MQTT_USERNAME | MQTT broker username | `<hostname>` |
| MQTT_PASSWORD | MQTT broker password | N/A |
| DISK_USAGE_PATHS | Comma-separated filesystem paths to report usage for | `/home` |
| PI_STATS_MOUNTS_JSON | JSON list of explicit mount source/read-write/directory checks | `[]` |
| PI_STATS_DISCOVERY_STATE_PATH | File used to track previously discovered components | `~/.cache/wg-scripts/pi_stats-discovery-components.json` |
| APT_CHECK_INTERVAL_SECONDS | How often to re-run `apt list --upgradable` | `21600` (6 hours) |

## Payload

Stats are published as non-retained JSON to `/homeassistant/<hostname>/stats` every
minute. The payload includes `wg_scripts_version` from the installed package. Disk
usage is a nested map of path to usage percentage, for example:

```json
{
  "wg_scripts_version": "1.3.1",
  "disk_usage": {
    "/home": 68.4,
    "/mnt/storage": 31.2
  }
}
```

Unavailable paths are logged and omitted from that sample without stopping the rest
of the stats payload.

### Mount health (optional)

`PI_STATS_MOUNTS_JSON` adds explicit mount checks that are independent of disk-usage
collection. For example:

```dotenv
PI_STATS_MOUNTS_JSON='[{"id":"vault_hdd","path":"/mnt/vault-hdd","source":"/dev/mapper/vault-hdd","required_directories":["pbs","immich"]},{"id":"vault_ssd","path":"/mnt/vault-ssd","source":"/dev/mapper/vault-ssd","required_directories":[]}]'
```

Each check requires an exact Linux mountpoint, the expected source, read/write mount
and superblock options, and every configured child directory. Local absolute sources
(such as device-mapper paths) are compared after resolving symlinks; non-path sources
(such as NFS exports) are compared literally. The state payload always includes
configured checks—even when they fail—under `mount_health`, with booleans, the
observed source, missing directories, and stable reason codes (`not_mounted`,
`wrong_source`, `read_only`, `missing_required_directories`, and
`inspection_error`). Invalid configuration fails before MQTT is touched.

When a Pi 5 Active Cooler (or compatible) exposes a `pwmfan` hwmon device, the
payload also includes:

| Key | Unit | Source |
|-----|------|--------|
| `fan_speed_rpm` | RPM | `/sys/class/hwmon/*/fan1_input` |
| `fan_pwm_percent` | % | `/sys/class/hwmon/*/pwm1` scaled from 0–255 |

These keys are omitted entirely on hosts without `pwmfan` (and for a sample if the
sysfs read fails).

### System health metrics

Every minute the payload also includes low-overhead host health fields:

| Key | Unit | Source |
|-----|------|--------|
| `throttled_flags` | int | `vcgencmd get_throttled` raw bitmask |
| `throttling_active` | bool | bits 0–3 currently set |
| `throttling_occurred` | bool | sticky bits 16–19 since boot |
| `cpu_frequency_mhz` | MHz | `psutil.cpu_freq().current` |
| `swap_usage` | % | `psutil.swap_memory().percent` |
| `cpu_iowait` | % | non-blocking `psutil.cpu_times_percent().iowait` |
| `network_interface` | — | primary NIC (matches `local_ip`, else first up physical) |
| `network_link_up` | bool | `psutil.net_if_stats()` for that NIC |
| `network_receive_bytes_per_second` | B/s | delta of `net_io_counters` between samples |
| `network_transmit_bytes_per_second` | B/s | delta of `net_io_counters` between samples |
| `pending_updates` | count | cached `apt list --upgradable` (no `apt update`) |
| `reboot_required` | bool | presence of `/var/run/reboot-required` |

Network byte rates are omitted from the first sample (no previous counter). Virtual
interfaces (`lo`, `docker*`, `br-*`, `veth*`, `tailscale*`, …) are skipped when
selecting the primary NIC.

`pending_updates` is refreshed at startup and then only every
`APT_CHECK_INTERVAL_SECONDS` (default six hours). That avoids a material CPU cost
from apt while still surfacing package debt. Failures to run apt omit the key for
that cycle without stopping stats publishing.

### SMART disks (optional)

When `smartctl` can enumerate and probe SMART-capable disks (NVMe / SATA SSD /
HDD — not SD cards), the payload includes a nested `smart` map keyed by device
slug:

```json
{
  "smart": {
    "dev_sda": {
      "health": "PASSED",
      "temperature": 38,
      "reallocated_sectors": 0
    },
    "dev_nvme0": {
      "health": "PASSED",
      "temperature": 41,
      "percentage_used": 2
    }
  }
}
```

| Key | Disks | Meaning |
|-----|-------|---------|
| `health` | All | `PASSED` / `FAILED` from SMART overall-health |
| `temperature` | All (when reported) | Drive temperature in °C |
| `reallocated_sectors` | ATA/SATA | Max of attributes 5 and 197 (reallocated / pending) |
| `percentage_used` | NVMe | SSD wear estimate from the NVMe health log |

SMART is sampled every five minutes (not every stats cycle). The entire `smart`
key is omitted on SD-only hosts, when `smartmontools` is missing, or when the
service user cannot run `smartctl` via sudo.

Detection uses `smartctl --scan-open` plus a `/sys/block` fallback that probes
common USB-SATA transports (`sat`, …). That covers bridges smartctl does not
auto-detect (for example JMicron `0x152d:0xa578` on vaultpi).

#### Enabling SMART on a Pi

1. Install tools: `sudo apt install smartmontools`
2. Grant the service user passwordless `smartctl`: `just setup-smart`
3. Restart the service: `just restart pi_stats`

`setup-smart` installs `/etc/sudoers.d/pi_stats-smartctl` (validated with
`visudo`) so the non-root service can run `sudo -n /usr/sbin/smartctl`.

## MQTT Discovery

On connect, `pi_stats` publishes a retained device-discovery payload to:

`homeassistant/device/<hostname>_pi_stats/config`

That creates one Home Assistant device containing:

- Fixed sensors with stable IDs (`sensor.<hostname>_cpu_usage`,
  `sensor.<hostname>_wg_scripts_version`, etc.)
- System-health sensors: CPU frequency, swap usage, I/O wait, network rates,
  pending updates
- Problem/connectivity binary sensors: throttling active / since boot, network
  link, reboot required
- One disk-usage sensor per `DISK_USAGE_PATHS` entry
- One diagnostic problem binary sensor per `PI_STATS_MOUNTS_JSON` entry
- Fan Speed / Fan PWM sensors when `pwmfan` hwmon is detected at startup
- Per SMART disk (when detected): health binary sensor, temperature, and wear

Disk entity IDs use path slugs:

| Path | Entity ID |
|------|-----------|
| `/` | `sensor.<hostname>_disk_usage_root` |
| `/home` | `sensor.<hostname>_disk_usage_home` |
| `/mnt/storage` | `sensor.<hostname>_disk_usage_mnt_storage` |

Mount entity IDs use the configured stable ID. For example, `vault_hdd` creates
`binary_sensor.<hostname>_mount_vault_hdd_problem`. The sensor is `on` when any
check fails and exposes the complete health object as entity attributes.

SMART entity IDs use device-path slugs (`/dev/sda` → `dev_sda`) for stability.
Friendly names come from smartctl `model_name` (for example
`Samsung SSD 850 EVO 500GB`); identical models are disambiguated with the
device basename.

| Metric | Entity ID | Example name |
|--------|-----------|--------------|
| Health | `binary_sensor.<hostname>_smart_dev_sda_health` | SMART Health (Samsung SSD 850 EVO 500GB) |
| Temperature | `sensor.<hostname>_smart_dev_sda_temperature` | SMART Temperature (Samsung SSD 850 EVO 500GB) |
| Reallocated sectors (ATA) | `sensor.<hostname>_smart_dev_sda_reallocated_sectors` | Reallocated Sectors (Samsung SSD 850 EVO 500GB) |
| SSD wear (NVMe) | `sensor.<hostname>_smart_dev_nvme0_percentage_used` | SSD Wear (SSD98-2563CG-PB) |

Health uses `device_class: problem` (`on` = `FAILED`). Duplicate normalized path
slugs are rejected at startup.

Discovery is republished after every MQTT connection and reconnection. Previously
published component IDs (and platforms) are stored locally so removing a disk path
or SMART device first publishes the Home Assistant removal tombstone, then the
clean discovery payload.

## Availability

Availability is published (retained) to:

`/homeassistant/<hostname>/pi_stats/availability`

| Event | Payload |
|-------|---------|
| Connected / running | `online` |
| Graceful shutdown | `offline` |
| Unexpected disconnect (MQTT LWT) | `offline` |

`sensor.<hostname>_cpu_usage` keeps `force_update: true` so template online sensors
that watch `last_changed` continue to refresh every minute.
