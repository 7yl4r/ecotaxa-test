SHELL := /bin/bash

.PHONY: help build sync setup start restart rebuild seed

help:
	@echo "Targets:"
	@echo "  make build    - docker compose build (syncs local patches into ecotaxaback/ecotaxafront first)"
	@echo "  make sync     - re-sync services/ecotaxa_back and services/ecotaxa_front patches into their docker/py/ build context"
	@echo "  make setup    - first-time setup: create DB, build schema, set admin creds, bring up the stack (./setup.sh)"
	@echo "  make start    - start/resume the already-installed stack without rebuilding (./start.sh)"
	@echo "  make restart  - rebuild images from current code and recreate containers, keeping DB/instance data"
	@echo "  make rebuild  - full rebuild: wipe DB + instance data (docker compose down -v), reseed from scratch (./reset.sh)"
	@echo "  make seed     - (re)generate and import the synthetic 'Seed Test Dataset' project (./seed.sh)"

# Re-sync patched local source into the two services whose Dockerfiles build
# from a docker/py/ copy rather than the repo root. Mirrors upstream's
# docker/build_prod.sh. ecotaxa_ML_back needs no equivalent step.
sync:
	cd services/ecotaxa_back/docker && rsync -avr --exclude-from=not_to_copy.lst ../py/ py/
	mkdir -p services/ecotaxa_back/docker/docker/prod_image
	cp services/ecotaxa_back/docker/prod_image/start.sh services/ecotaxa_back/docker/docker/prod_image/
	cd services/ecotaxa_front/docker && rsync -avr --exclude=docker --exclude-from=not_to_copy.lst .. py/

build: sync
	docker compose build

setup:
	./setup.sh

start:
	./start.sh

# Apply code changes without losing data: sync patches, rebuild images, and
# recreate only the containers whose image/config changed. No `down -v` and
# no clearing of bind-mounted data dirs, so pgdata/vault/ftp_area/etc. persist.
restart: sync
	docker compose build
	docker compose up -d

# Full rebuild: wipes the DB (named volume) and all instance data (bind
# mounts), rebuilds the stack from scratch, and reseeds the test dataset.
rebuild:
	./reset.sh

seed:
	./seed.sh
