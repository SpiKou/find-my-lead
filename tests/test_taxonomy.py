import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import taxonomy  # noqa: E402


def test_taxonomy_csvs_are_consistent():
    assert taxonomy.validate() == []
