
disable:
	sudo systemctl disable dehumidifier_controller.service

enable:
	sudo systemctl enable dehumidifier_controller.service

install:
	sudo cp dehumidifier_controller.service /etc/systemd/system/
	sudo systemctl daemon-reload

restart:
	sudo systemctl restart dehumidifier_controller.service

setup:
	$(MAKE) install
	$(MAKE) enable
	$(MAKE) restart

start:
	sudo systemctl start dehumidifier_controller.service

stop:
	sudo systemctl stop dehumidifier_controller.service

tail:
	clear && sudo journalctl -u dehumidifier_controller.service -f -n 50
