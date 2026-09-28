"""Заготовка: резервная копия баз и бакетов."""

import sys

from _common import not_implemented

WHAT = "дамп баз plandb, sitedb, analysisdb и зеркало бакетов S3 в backup/YYYY-MM-DD/"

if __name__ == "__main__":
    sys.exit(not_implemented("backup.py", "не запланирована", WHAT))
