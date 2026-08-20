#!/usr/bin/env python3
"""
Talks to a running EcoTaxa stack's API to:
  1. log in as the administrator
  2. pull the taxonomy tree from EcoTaxoServer (idempotent -- fast after the
     first run, needed so the category ids used in the generated TSVs
     resolve to something)
  3. delete any previous run of the seed project (so this script is safe to
     re-run any number of times without piling up duplicate projects)
  4. create a fresh project and import seed/build/../file_srv/seed_dataset.zip
     (built by generate_dataset.py) into it
  5. poll the import job until it finishes and print a summary

Run generate_dataset.py first (seed.sh does both, in order).
"""
import os
import sys
import time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent

PROJECT_TITLE = os.environ.get("SEED_PROJECT_TITLE", "Seed Test Dataset")


def load_env():
    env = dict(os.environ)
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env.setdefault(k.strip(), v.strip())
    return env


def wait_for_backend(base_url, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(base_url + "/status", timeout=5)
            if r.status_code < 500:
                return
        except requests.RequestException:
            pass
        time.sleep(2)
    raise SystemExit(f"Backend at {base_url} never became reachable")


def login(base_url, email, password):
    r = requests.post(
        base_url + "/login", json={"username": email, "password": password}
    )
    r.raise_for_status()
    token = r.json()
    return {"Authorization": f"Bearer {token}"}


def pull_taxonomy(base_url, headers):
    print("==> Pulling taxonomy from EcoTaxoServer (skips fast if already up to date)...")
    r = requests.get(base_url + "/taxa/pull_from_central", headers=headers, timeout=180)
    r.raise_for_status()
    result = r.json()
    print(f"    {result}")
    if result.get("error"):
        raise SystemExit(f"Taxonomy pull failed: {result['error']}")


def delete_existing_project(base_url, headers):
    r = requests.get(base_url + "/projects", headers=headers, params={"fields": "projid,title"})
    r.raise_for_status()
    for prj in r.json():
        if prj.get("title") == PROJECT_TITLE:
            pid = prj["projid"]
            print(f"==> Deleting previous '{PROJECT_TITLE}' project (id={pid})...")
            dr = requests.delete(base_url + f"/projects/{pid}", headers=headers)
            dr.raise_for_status()


def create_project(base_url, headers):
    r = requests.post(
        base_url + "/projects/create",
        headers=headers,
        json={"title": PROJECT_TITLE, "instrument": "Other camera", "access": "1"},
    )
    r.raise_for_status()
    return r.json()


def start_import(base_url, headers, project_id, source_path):
    r = requests.post(
        base_url + f"/file_import/{project_id}",
        headers=headers,
        json={"source_path": source_path},
    )
    r.raise_for_status()
    body = r.json()
    if body.get("errors"):
        raise SystemExit(f"Import request rejected: {body['errors']}")
    return body["job_id"]


def poll_job(base_url, headers, job_id):
    last_msg = None
    while True:
        r = requests.get(base_url + f"/jobs/{job_id}/", headers=headers)
        r.raise_for_status()
        job = r.json()
        state = job["state"]
        msg = f"{job.get('progress_pct', 0)}% {job.get('progress_msg', '')}"
        if msg != last_msg:
            print(f"    [{state}] {msg}")
            last_msg = msg
        if state == "F":
            return job
        if state == "E":
            raise SystemExit(f"Import job failed: {job.get('errors')}")
        if state == "A":
            raise SystemExit(
                "Import job is asking for input (unresolved user/taxon) -- "
                f"question: {job.get('question')}. The seed dataset should "
                "never hit this; check generate_dataset.py's category ids."
            )
        time.sleep(1)


def main():
    env = load_env()
    base_url = env.get("ECOTAXA_URL", "http://localhost:8088/api")
    admin_email = env.get("ADMIN_EMAIL", "administrator@mail.test")
    admin_password = env.get("ADMIN_PASSWORD")
    if not admin_password:
        raise SystemExit("ADMIN_PASSWORD not set (check .env, or run setup.sh first)")

    zip_path = REPO_ROOT / "file_srv" / "seed_dataset.zip"
    if not zip_path.exists():
        raise SystemExit(f"{zip_path} not found -- run generate_dataset.py first")

    print(f"==> Waiting for backend at {base_url}...")
    wait_for_backend(base_url)

    print(f"==> Logging in as {admin_email}...")
    headers = login(base_url, admin_email, admin_password)

    pull_taxonomy(base_url, headers)

    delete_existing_project(base_url, headers)

    print(f"==> Creating project '{PROJECT_TITLE}'...")
    project_id = create_project(base_url, headers)
    print(f"    project id = {project_id}")

    print("==> Starting import of seed_dataset.zip...")
    job_id = start_import(base_url, headers, project_id, "/seed_dataset.zip")
    print(f"    job id = {job_id}")
    job = poll_job(base_url, headers, job_id)

    print()
    print("Seed import complete.")
    print(f"  Project:  {PROJECT_TITLE} (id={project_id})")
    print(f"  Rows:     {job.get('result', {})}")
    print(f"  URL:      http://localhost:8088")


if __name__ == "__main__":
    main()
