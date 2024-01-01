#!/bin/bash

systemctl stop enclosure_monitor.service || :

cp enclosure_monitor.service /etc/systemd/system/

echo "Service file copied to /etc/systemd/system/enclosure_monitor.service"

systemctl disable enclosure_monitor.service

systemctl enable enclosure_monitor.service

systemctl start enclosure_monitor.service
