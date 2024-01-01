#!/bin/bash

cp pi_stats.service /etc/systemd/system/

echo "Service file copied to /etc/systemd/system/pi_stats.service"

systemctl disable pi_stats.service

systemctl daemon-reload

systemctl enable pi_stats.service

systemctl start pi_stats.service
