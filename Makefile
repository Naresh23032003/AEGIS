.PHONY: up down contracts contracts-python contracts-ts test test-python test-ts opa-test \
        e2e e2e-live record-fixtures lint lint-python lint-ts venv env

COMPOSE := docker compose -f deploy/docker-compose.yml
PY := .venv/bin/python
PIP := .venv/bin/pip
OPA := $(shell scripts/ensure-opa.sh)

venv:
	@if [ -d .venv ]; then exit 0; fi; \
	if command -v python3.12 >/dev/null 2>&1; then PYBIN=python3.12; \
	elif command -v pyenv >/dev/null 2>&1 && pyenv versions --bare | grep -q '^3.12'; then \
		PYBIN="$$(pyenv root)/versions/$$(pyenv versions --bare | grep '^3.12' | tail -1)/bin/python3"; \
	else echo "python3.12 not found; install it (e.g. pyenv install 3.12.3)" >&2; exit 1; fi; \
	$$PYBIN -m venv .venv
	$(PIP) install --upgrade pip -q
	$(PIP) install -r requirements-dev.txt -q

env:
	[ -f .env ] || cp .env.example .env

# `contracts` (host-side codegen, see contracts-python below) needs
# .venv/bin/datamodel-codegen; a clean clone has no .venv yet, so `up` must
# provision it first or the phase 6 stranger test (clone -> make up ->
# healed incident, Docker + Python 3.12 only) fails before Docker even
# starts. Found by timing a cold clone for the phase 6 report.
up: env venv contracts
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down -v

contracts: contracts-python contracts-ts

contracts-python:
	./packages/contracts/scripts/gen_python.sh

contracts-ts:
	npm run gen -w @aegis/contracts

test: test-python test-ts opa-test

test-python:
	$(PY) -m pytest apps/core -q

test-ts:
	npx -w @aegis/console tsc --noEmit
	npx -w @aegis/contracts tsc --noEmit
	npm run test -w @aegis/console

opa-test:
	$(OPA) test packages/policies -v

lint: lint-python lint-ts

lint-python:
	.venv/bin/ruff check .
	.venv/bin/mypy

lint-ts:
	npm run lint
	npm run format:check

# e2e: scenario suite against a running stack (`make up` first). MOCK_LLM
# is inherited from the shell so `MOCK_LLM=1 make e2e` runs on fixtures.
e2e:
	$(PY) -m pytest e2e -q

e2e-live:
	MOCK_LLM=0 $(PY) -m pytest e2e -q

record-fixtures:
	$(PY) scripts/record_fixtures.py $(SCENARIO)
