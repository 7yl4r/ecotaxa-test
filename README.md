# EcoTaxa (self-hosted)

Docker Compose stack for a local/self-hosted EcoTaxa instance, adapted from
the official ["all_in_one"](https://github.com/ecotaxa/ecotaxa_front/tree/master/docker/all_in_one)
example maintained by the EcoTaxa team.

## Services

- **nginx** — reverse proxy in front of everything, exposed on `:8088`.
- **ecotaxafront** ([ecotaxa_front](https://github.com/ecotaxa/ecotaxa_front)) — Angular UI, served via uwsgi.
- **ecotaxaback** ([ecotaxa_back](https://github.com/ecotaxa/ecotaxa_back)) — FastAPI/Flask API, image vault, jobs.
- **ecotaxagpuback** (optional, `--profile gpu`) — GPU-accelerated prediction/segmentation backend. Needs an NVIDIA GPU + NVIDIA Container Toolkit.
- **pgdb** — PostgreSQL 14 with pgvector, the application database.

All service images are the official ones published by the EcoTaxa team on
Docker Hub (`ecotaxa/ecotaxa_front`, `ecotaxa/ecotaxa_back`,
`ecotaxa/ecotaxa_gpu_back`).

## First run

```sh
./setup.sh
```

This starts postgres, creates the `ecotaxa` database, builds the schema, sets
the administrator credentials, then brings up the full stack. It prints the
admin login at the end.

Then open **http://localhost:8088**.

## Subsequent runs

```sh
./start.sh
# or
docker compose up -d
```

## Optional: GPU back-end

```sh
docker compose --profile gpu up -d
```

## Test dataset

`seed/` generates a deterministic synthetic dataset (fixed random seed) and
imports it into a project called **"Seed Test Dataset"**: 600 objects across
3 sample stations and 26 real plankton taxa (pulled from EcoTaxoServer),
~73% `validated` / ~27% `predicted`. Each object also gets 9 numeric
"morphometric" columns (area, major/minor axis, elongation, ...) computed
from its actual generated image, so there's real per-category signal to
build train/test-split and model-evaluation UI against.

```sh
./seed.sh
```

Safe to re-run any time — it deletes the previous "Seed Test Dataset"
project and rebuilds it from scratch with the same seed, so the data is
identical on every run. It needs the stack up and the admin account created
first (`./setup.sh`), and network access to `ecotaxoserver.obs-vlfr.fr` (the
public EcoTaxa taxonomy server) the first time it pulls taxonomy — after
that the pull is a fast no-op.

### Full rebuild loop (for frontend iteration)

```sh
./reset.sh
```

Wipes the DB and all instance data (`docker compose down -v` + clears the
bind-mounted data dirs), brings the stack back up, and reseeds the test
dataset. This is the one-command "give me a clean instance" reset while
developing the test/train split feature.

To tweak the generated dataset (object count, category list, validated/predicted
split), edit `seed/generate_dataset.py` — see `SEED_OBJECT_COUNT` and
`SEED_VALIDATED_FRACTION` env vars, or the `CATEGORIES`/`SAMPLES` lists directly.

## Configuration

- `back_config.ini` — back-end config (DB connection, vault paths, secrets). Mounted read-only into `ecotaxaback` as `/config.ini`.
- `front_config/` — front-end config, including `config.cfg` (must share `SECRET_KEY` / `MAILSERVICE_SECRET_KEY` with `back_config.ini`) and customizable home-page HTML snippets.
- `nginx.conf` — reverse proxy config. Not production-hardened (no TLS) — put a real reverse proxy in front if exposing this beyond your local network.
- `.env` — `DB_PASSWORD` used by the `pgdb` container; must match `DB_PASSWORD` in `back_config.ini`.

Data persists in these bind-mounted directories:

- `vault/` — uploaded images
- `ftp_area/` — exports
- `file_srv/` — files readable by all users ("the server")
- `models/` — CNN models
- `eco_users_files/` — per-user file areas

Postgres data persists in the named volume `pgdata`.

## Notes

- Secrets in `back_config.ini`, `front_config/config.cfg`, and `.env` were
  randomly generated for this instance — don't reuse them elsewhere, and
  change the administrator password after first login.
- `TAXOSERVER_URL` points at the public EcoTaxoServer taxonomy instance
  (`https://ecotaxoserver.obs-vlfr.fr`); this is normal for the all_in_one
  setup and just gives you the shared taxonomy tree.
