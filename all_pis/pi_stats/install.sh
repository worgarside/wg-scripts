#!/bin/bash

cp pi_stats.service /etc/systemd/system/
echo "Service file copied to /etc/systemd/system/pi_stats.service"
systemctl reenable pi_stats.service
systemctl start pi_stats.service
