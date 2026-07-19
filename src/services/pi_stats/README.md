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
| PI_STATS_DISCOVERY_STATE_PATH | File used to track previously discovered components | `~/.cache/wg-scripts/pi_stats-discovery-components.json` |

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

## MQTT Discovery

On connect, `pi_stats` publishes a retained device-discovery payload to:

`homeassistant/device/<hostname>_pi_stats/config`

That creates one Home Assistant device containing:

- Fixed sensors with stable IDs (`sensor.<hostname>_cpu_usage`,
  `sensor.<hostname>_wg_scripts_version`, etc.)
- One disk-usage sensor per `DISK_USAGE_PATHS` entry

Disk entity IDs use path slugs:

| Path | Entity ID |
|------|-----------|
| `/` | `sensor.<hostname>_disk_usage_root` |
| `/home` | `sensor.<hostname>_disk_usage_home` |
| `/mnt/storage` | `sensor.<hostname>_disk_usage_mnt_storage` |

Duplicate normalized path slugs are rejected at startup.

Discovery is republished after every MQTT connection and reconnection. Previously
published component IDs are stored locally so removing a disk path first publishes
the Home Assistant removal tombstone, then the clean discovery payload.

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
