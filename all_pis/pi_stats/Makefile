
disable:
	sudo systemctl disable pi_stats.service

enable:
	sudo systemctl enable pi_stats.service

install:
	sudo cp pi_stats.service /etc/systemd/system/
	sudo systemctl daemon-reload

restart:
	sudo systemctl restart pi_stats.service

setup:
	$(MAKE) install
	$(MAKE) enable
	$(MAKE) restart

start:
	sudo systemctl start pi_stats.service

stop:
	sudo systemctl stop pi_stats.service

tail:
	clear && sudo journalctl -u pi_stats.service -f -n 50
