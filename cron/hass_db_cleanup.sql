DELETE
FROM states
WHERE state = 'unknown'
   OR (entity_id = 'sensor.battery_sheena' AND state = '0')
   OR (entity_id = 'sensor.battery_will' AND state = '0');