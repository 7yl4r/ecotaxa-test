# EcoTaxa (self-hosted)

Docker Compose stack for a local/self-hosted EcoTaxa instance, adapted from
the official ["all_in_one"](https://github.com/ecotaxa/ecotaxa_front/tree/master/docker/all_in_one)
example maintained by the EcoTaxa team.

## Services

- **nginx** — reverse proxy in front of everything, exposed on `:8088`.
- **ecotaxafront** ([ecotaxa_front](https://github.com/ecotaxa/ecotaxa_front)) — Angular/Flask UI, served via uwsgi.
- **ecotaxaback** ([ecotaxa_back](https://github.com/ecotaxa/ecotaxa_back)) — FastAPI API, image vault, jobs.
- **ecotaxagpuback** ([ecotaxa_ML_back](https://github.com/ecotaxa/ecotaxa_ML_back)) — ML back-end. Polls the shared job table directly and runs `Prediction` jobs (Random Forest training/classification, plus deep-CNN feature extraction if a GPU is available). Without deploying this, Prediction jobs sit pending forever — `ecotaxaback` deliberately excludes them from its own scheduler. Runs CPU-only here (no GPU on this host); only the "Add deep features" option in the Prediction wizard needs a real GPU.
- **pgdb** — PostgreSQL 14 with pgvector, the application database.

`ecotaxaback`, `ecotaxafront`, and `ecotaxagpuback` are built from patched
local source in `services/` rather than pulled from Docker Hub — see
[Local patches](#local-patches-to-vendored-source) below.

## First run

```sh
make build
make setup
# or, equivalently:
docker compose build
./setup.sh
```

The build compiles all three app services from source (the ML back-end in
particular is a slow, multi-GB build the first time — CUDA base image +
TensorFlow). `setup.sh` then starts postgres, creates the `ecotaxa`
database, builds the schema, sets the administrator credentials, and brings
up the full stack. It prints the admin login at the end.

Then open **http://localhost:8088**.

## Subsequent runs

```sh
make start
# or
./start.sh
# or
docker compose up -d
```

## Makefile

| Target | Does | Data |
| --- | --- | --- |
| `make build` | `sync` + `docker compose build` (all three app services from source) | n/a |
| `make sync` | Re-copies patched `services/ecotaxa_back` / `services/ecotaxa_front` source into the `docker/py/` copy their Dockerfiles actually build from — see [Local patches](#local-patches-to-vendored-source) | n/a |
| `make setup` | First-time install: DB + schema + admin credentials + full stack (`./setup.sh`) | creates |
| `make start` | Start/resume the already-installed stack, no rebuild (`./start.sh`) | preserved |
| `make restart` | **Apply code changes, keep data.** `sync` + `docker compose build` + `docker compose up -d`, recreating only the containers whose image changed | preserved |
| `make rebuild` | **Full rebuild, wipes data.** `docker compose down -v`, clears the bind-mounted data dirs, re-runs `setup` and `seed` from scratch (`./reset.sh`) | **wiped** |
| `make seed` | (Re)generate and import the synthetic "Seed Test Dataset" project (`./seed.sh`) | modifies (that project only) |

`make restart` is the one to reach for after editing any of the patched
services (`services/ecotaxa_back`, `services/ecotaxa_front`,
`services/ecotaxa_ML_back`) — it picks up the code change and recreates the
affected container(s) in place, leaving `pgdata` and the bind-mounted
`vault/`, `ftp_area/`, `file_srv/`, `models/`, `eco_users_files/` untouched.
`make rebuild` is the "start over completely" button: it destroys the
postgres volume and clears those same directories before reinstalling and
reseeding, for when you want a guaranteed-clean instance rather than an
incremental update.

## Test dataset

`seed/` generates a deterministic synthetic dataset (fixed random seed) and
imports it into a project called **"Seed Test Dataset"**: 600 objects across
3 sample stations and 26 real plankton taxa (pulled from EcoTaxoServer),
~73% `validated` / ~27% `predicted`. Each object also gets 11 numeric
"morphometric" columns (area, major/minor axis, elongation, perimeter,
circularity, ...) computed from its actual generated image, so there's real
per-category signal for the Prediction wizard's classifier to actually learn
from — and enough free columns (≥10) for the project to show up as its own
candidate source project in that wizard.

```sh
make seed
# or
./seed.sh
```

Safe to re-run any time — it deletes the previous "Seed Test Dataset"
project and rebuilds it from scratch with the same seed, so the data is
identical on every run. It needs the stack up and the admin account created
first (`./setup.sh`), and network access to `ecotaxoserver.obs-vlfr.fr` (the
public EcoTaxa taxonomy server) the first time it pulls taxonomy — after
that the pull is a fast no-op.

### Restarting after code changes (keeps data)

```sh
make restart
```

Re-syncs the patched `ecotaxa_back`/`ecotaxa_front` source, rebuilds any
images whose code changed, and recreates just those containers with
`docker compose up -d`. `pgdata` and the bind-mounted data dirs are left
alone, so the admin account and "Seed Test Dataset" project survive. Use
this after editing anything under `services/`.

### Full rebuild loop (wipes data, for a guaranteed-clean instance)

```sh
make rebuild
# or
./reset.sh
```

Wipes the DB and all instance data (`docker compose down -v` + clears the
bind-mounted data dirs), brings the stack back up, and reseeds the test
dataset. This is the one-command "give me a clean instance" reset while
developing the test/train split feature.

To tweak the generated dataset (object count, category list, validated/predicted
split), edit `seed/generate_dataset.py` — see `SEED_OBJECT_COUNT` and
`SEED_VALIDATED_FRACTION` env vars, or the `CATEGORIES`/`SAMPLES` lists directly.

## Prediction & train/test-split evaluation

`/Job/Create/Prediction?projid=<id>` walks through: pick source project(s) →
pick categories → pick features & settings → run. The "Choice of features
and settings" step has a **"Held-out test %"** field (0–50%, default 0). When
set, a stratified sample of that fraction of the learning set (per category)
is held out, a classifier is trained on the rest, and its accuracy is
measured against the held-out objects — reported per-taxon and overall on
the job's monitor page — before the real classifier (always trained on the
*full* learning set) classifies the target project's unclassified objects.
Categories with fewer than 2 validated examples can't be evaluated (still
used for training) and are called out separately in the result.

This only exercises the classical Random-Forest path; "Add deep features"
needs a real GPU running the ML back-end and isn't covered by the CPU-only
setup here.

## Local patches to vendored source

`services/ecotaxa_back`, `services/ecotaxa_front`, `services/ecotaxa_ML_back`
are patched clones of the upstream repos (not submodules — `.git` stripped).
Patches so far: `test_fraction` added to the `PredictionReq` API model in
both `ecotaxa_back` and `ecotaxa_ML_back`; the actual split/evaluate logic in
`ecotaxa_ML_back`'s `API_operations/GPU_Prediction.py`; the wizard UI field
and results table in `ecotaxa_front`'s `appli/jobs/by_type/Prediction.py` +
`appli/templates/jobs/prediction_create_settings.html` + the hand-patched
generated client `to_back/ecotaxa_cli_py/models/prediction_req.py`.

`ecotaxaback`/`ecotaxafront`'s Dockerfiles expect their build context to be
their own `docker/` folder with a `docker/py/` copy of the app source
present (that's what upstream's `docker/build_prod.sh` does via `rsync`,
normally driven off `git status`). Re-sync after further edits to those two
services with:

```sh
make sync
# or, equivalently:
cd services/ecotaxa_back/docker && rsync -avr --exclude-from=not_to_copy.lst ../py/ py/
mkdir -p docker/prod_image && cp prod_image/start.sh docker/prod_image/
cd services/ecotaxa_front/docker && rsync -avr --exclude=docker --exclude-from=not_to_copy.lst .. py/
```

then `docker compose build ecotaxaback ecotaxafront` (or just `make build` /
`make restart`, which run `sync` first automatically). `ecotaxa_ML_back`
doesn't need this — its Dockerfile builds straight from the repo root.

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
