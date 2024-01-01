#!/bin/bash

systemctl stop climate_monitor.service || :

cp climate_monitor.service /etc/systemd/system/

echo "Service file copied to /etc/systemd/system/climate_monitor.service"

systemctl disable climate_monitor.service

systemctl daemon-reload

systemctl enable climate_monitor.service

systemctl start climate_monitor.service
