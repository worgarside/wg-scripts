PYTHON_VERSION ?= 3.11

clean:
	sudo rm -rf .venv

create-env:
	virtualenv -p $(PYTHON_VERSION) .venv
	$(MAKE) install

install:
	.venv/bin/pip install -r requirements.txt

update:
	git add .
	git stash save "Stash before update @ $(shell date)"
	git pull --prune
	@$(MAKE) install
