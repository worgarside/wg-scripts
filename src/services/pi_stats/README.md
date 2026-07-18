# Pi Stats

Reports system stats to an MQTT broker.

## Environment Variables

| Name | Description | Default |
|------|-------------|---------|
| HOSTNAME | The Pi's hostname | `<hostname>` |
| MQT_HOST | MQTT broker host | N/A |
| MQTT_USERNAME | MQTT broker username | `<hostname>` |
| MQTT_PASSWORD | MQTT broker password | N/A |
| DISK_USAGE_PATHS | Comma-separated filesystem paths to report usage for | `/home` |

## Payload

Stats are published as JSON to `/homeassistant/<hostname>/stats`. Disk usage is a
nested map of path to usage percentage, for example:

```json
{
  "disk_usage": {
    "/home": 68.4,
    "/mnt/storage": 31.2
  }
}
```

Unavailable paths are logged and omitted from that sample without stopping the rest
of the stats payload.
