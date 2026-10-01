.PHONY: setup dev api bot admin worker migrate test lint smoke backup restore import export seed-demo

PYTHON ?= python

setup:
	$(PYTHON) scripts/setup.py

dev:
	$(PYTHON) -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

api:
	$(PYTHON) -m uvicorn app.main:app --host 127.0.0.1 --port 8000

admin:
	@echo "Admin Console is mounted inside FastAPI app at http://127.0.0.1:8000/admin"
	$(PYTHON) -m uvicorn app.main:app --host 127.0.0.1 --port 8000

bot:
	$(PYTHON) -m app.bot.main

worker:
	$(PYTHON) -m app.jobs.worker

migrate:
	$(PYTHON) -m alembic upgrade head

test:
	$(PYTHON) -m pytest tests -v

lint:
	$(PYTHON) -m pytest tests --collect-only

smoke:
	$(PYTHON) scripts/smoke_test.py

backup:
	$(PYTHON) scripts/backup.py create

restore:
	$(PYTHON) scripts/restore.py --file "$(BACKUP_ID)"

import:
	$(PYTHON) scripts/import_cli.py --file "$(FILE)" --entity "$(ENTITY)"

export:
	$(PYTHON) scripts/export_cli.py --entity "$(ENTITY)"

seed-demo:
	$(PYTHON) scripts/seed_demo.py
