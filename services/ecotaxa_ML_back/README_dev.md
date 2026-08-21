# Development Environment Setup for EcoTaxa ML Backend

This document provides instructions for setting up a development environment for the EcoTaxa ML Backend.

## Prerequisites

- **Python 3.8**: The project is strictly pinned to Python 3.8.
- **PostgreSQL**: Installation of PostgreSQL binaries (version 10+). A running instance is not required for tests, as they can create a temporary database from scratch if `initdb` and `pg_ctl` are available.
- **GPU (Optional but recommended)**: For running ML tasks efficiently. Requires NVIDIA drivers and CUDA 11.4 compatible toolkit.

## Installation

### 1. Clone the repository
```bash
git clone <repository_url>
cd ecotaxa_ML_back
```

### 2. Create a virtual environment
```bash
python3.8 -m venv venv38
source venv38/bin/activate
```

### 3. Install dependencies
Install the project in editable mode with development dependencies. 
**Note:** `imgaug` must be compiled from source to avoid compatibility issues.

```bash
pip install --upgrade pip wheel setuptools
pip install -e ".[dev]" --no-binary=imgaug
```

## Configuration

Copy the template configuration file and adjust it to your environment:

```bash
cp src/config.ini.template src/config.ini # Or any local path
```

Edit the configuration with your database credentials and local paths:
- `DB_*`: Connection details for your PostgreSQL instance.
- `VAULT_DIR`: Path to the image vault.
- `JOBS_DIR`: Path where temporary job data will be stored.
- `MODELSAREA`: Path to pre-trained CNN models.

## Development Tasks

### Running Tests
We use `pytest` for testing. 

The tests are designed to run without a pre-existing database. They use the PostgreSQL binaries (`initdb`, `pg_ctl`) to create, start, and populate a temporary database instance for the duration of the test session.

You can run all tests using:

```bash
pytest
```

Alternatively, you can use `tox` to run tests and linting in a clean environment:
```bash
tox
```

**Note:** If your PostgreSQL binaries are not in the default system path, the tests might expect them in a specific location (e.g., `/usr/lib/postgresql/<version>/bin/`). You may need to adjust `tests/tools/dbBuildSQL.py` if they are installed elsewhere.

### Linting and Type Checking
We use `mypy` for static type checking:

```bash
mypy src
```

### Code Coverage
To generate a coverage report:
```bash
pytest --cov=src --cov-report=html
```
The report will be available in the `htmlcov/` directory.

## Continuous Integration and Delivery

### Docker Image Publishing

The project uses GitHub Actions to automatically build and publish Docker images to Docker Hub.

- **Trigger**: A new Docker image is built and pushed whenever a git tag starting with `v` (e.g., `v1.0.0`) is pushed to the repository.
- **Workflow**: Defined in `.github/workflows/build_docker.yml`.
- **Image Name**: `ecotaxa/ecotaxa_ml_back:<tag_name>`
- **Dockerfile**: Uses `./docker/prod_image/Dockerfile`.

To release a new version:
1. Ensure the code is ready and tested.
2. Create a new tag: `git tag v1.2.3`
3. Push the tag: `git push origin v1.2.3`
4. Monitor the "Actions" tab on GitHub for the build status.

## Running the Application

The main entry point for the background worker is `ml_jobs_runner.py`. It polls the database for pending jobs.

```bash
# Example if using src/config.ini
export APP_CONFIG='src/config.ini'
python src/ml_jobs_runner.py
```

## Docker Development

If you prefer using Docker, there are helper scripts in the `docker/` directory:
- `docker/run_ml_docker.sh`: Run the published images in a container.
- `docker/run_ml_docker_dev.sh`: Run a local docker image for testing purposes.

**Note:** These scripts are provided as examples and contain hardcoded paths to local, unversioned files (like `config.ini` and data volumes). You will likely need to adjust the `--mount` paths in these scripts to match your local environment before using them.
