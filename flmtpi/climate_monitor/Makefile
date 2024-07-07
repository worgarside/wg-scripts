
disable:
	sudo systemctl disable climate_monitor.service

enable:
	sudo systemctl enable climate_monitor.service

install:
	sudo cp climate_monitor.service /etc/systemd/system/
	sudo systemctl daemon-reload

restart:
	sudo systemctl restart climate_monitor.service

setup:
	$(MAKE) install
	$(MAKE) enable
	$(MAKE) restart

start:
	sudo systemctl start climate_monitor.service

stop:
	sudo systemctl stop climate_monitor.service

tail:
	clear && sudo journalctl -u climate_monitor.service -f -n 50
