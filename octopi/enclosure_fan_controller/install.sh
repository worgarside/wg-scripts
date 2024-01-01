#!/bin/bash

systemctl stop enclosure_fan_controller.service || :

cp enclosure_fan_controller.service /etc/systemd/system/

echo "Service file copied to /etc/systemd/system/enclosure_fan_controller.service"

systemctl disable enclosure_fan_controller.service

systemctl enable enclosure_fan_controller.service

systemctl start enclosure_fan_controller.service
