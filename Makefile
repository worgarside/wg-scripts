create-env:
	virtualenv -p 3.11 .venv
	$(MAKE) install

install:
	.venv/bin/pip install -r requirements.txt

update:
	git add .
	git stash save "Stash before update @ $(shell date)"
	git pull --prune
	@$(MAKE) install
