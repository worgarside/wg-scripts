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
	@$(MAKE) install


# Service Commands

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

stop-%:
	sudo systemctl stop $*.service

tail-%:
	clear && sudo journalctl -u $*.service -f -n 50
