#!/bin/bash

systemctl stop fan_controller.service || :

cp fan_controller.service /etc/systemd/system/

echo "Service file copied to /etc/systemd/system/fan_controller.service"

systemctl disable fan_controller.service

systemctl enable fan_controller.service

systemctl start fan_controller.service
