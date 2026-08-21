# -*- coding: utf-8 -*-
from os.path import dirname, realpath
from pathlib import Path

# All files paths are now relative to root shared directory
TEST_DIR = Path(dirname(realpath(__file__))).resolve()
SHARED_DIR = (Path(dirname(realpath(__file__))) / ".." / "data").resolve()
FTP_DIR = SHARED_DIR / "ftp"
