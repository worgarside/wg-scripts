# DHT22 MQTT Sensor

Reads values from a DHT22 sensor and sends them to an MQTT broker.

## Environment Variables

| Name | Description | Default |
|------|-------------|---------|
| HOSTNAME | The Pi's hostname | `<hostname>` |
| DHT22_PIN | GPIO pin number connected to the DHT22 sensor | N/A |
| MQT_HOST | MQTT broker host | N/A |
| MQTT_USERNAME | MQTT broker username | `<hostname>` |
| MQTT_PASSWORD | MQTT broker password | N/A |
