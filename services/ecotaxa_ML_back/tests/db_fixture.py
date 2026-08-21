# Fixture for ensuring we have the DB up and running
from os.path import dirname, realpath
from pathlib import Path
from typing import Any, Generator

import pytest

from API_operations.helpers.Service import Service
from data.db_load import do_load
from tools.dbBuildSQL import EcoTaxaDBFrom0

HERE = Path(dirname(realpath(__file__)))
PG_DIR = HERE / "pg_files"
CONF_FILE = HERE / "config.ini"


@pytest.fixture(scope="session")
def database(config) -> Generator[EcoTaxaDBFrom0, Any, None]:
    # Setup
    db = EcoTaxaDBFrom0(PG_DIR, CONF_FILE)
    db.create()
    with Service() as sce:
        do_load(sce.session)
    yield db
    # Teardown
    db.cleanup()
