PYTHON_VERSION ?= 3.12

clean:
	sudo rm -rf .venv

create-env:
	virtualenv -p $(PYTHON_VERSION) .venv
	$(MAKE) install-python

install-python:
	.venv/bin/pip install -r requirements.txt

update:
	git add .
	git stash save "Stash before update @ $(shell date)"
	git pull --prune
	@$(MAKE) install-python

# Service Commands

SERVICES := $(shell ls -d */ | cut -f1 -d'/')

include .env
export

run-%:
	.venv/bin/python $*/main.py

disable-%:
	sudo systemctl disable $*.service

enable-%:
	sudo systemctl enable $*.service

install-%:
	cd $*; \
	sudo cp $*.service /etc/systemd/system/; \
	sudo systemctl daemon-reload

restart-%:
	sudo systemctl restart $*.service

setup-%:
	$(MAKE) install-$*
	$(MAKE) enable-$*
	$(MAKE) restart-$*

start-%:
	sudo systemctl start $*.service

status-%:
	sudo systemctl status $*.service

stop-%:
	sudo systemctl stop $*.service

tail-%:
	clear && sudo journalctl -u $*.service -f -n 50

stop-all:
	@for service in $(SERVICES); do \
		if sudo systemctl list-unit-files | grep -q "$$service.service"; then \
			echo "Stopping $$service.service"; \
			sudo systemctl stop $$service.service; \
		else \
			echo "$$service.service is not installed"; \
		fi \
	done

status-all:
	@for service in $(SERVICES); do \
		if sudo systemctl list-unit-files | grep -q "$$service.service"; then \
			echo "$$service.service is $$(systemctl is-active $$service.service) and $$(systemctl is-enabled $$service.service)"; \
		else \
			echo "$$service.service is not installed"; \
		fi \
	done

restart-all:
	@for service in $(SERVICES); do \
		if sudo systemctl list-unit-files | grep -q "$$service.service"; then \
			echo "Restarting $$service.service"; \
			sudo systemctl restart $$service.service; \
		else \
			echo "$$service.service is not installed"; \
		fi \
	done
