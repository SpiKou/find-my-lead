import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import lighthouse  # noqa: E402


def test_parse_scores():
    data = {"lighthouseResult": {"categories": {
        "performance": {"score": 0.42}, "accessibility": {"score": 0.9},
        "best-practices": {"score": 0.785}, "seo": {"score": 1},
    }}}
    assert lighthouse.parse(data) == {
        "performance": 42, "accessibility": 90, "best_practices": 78, "seo": 100, "error": None,
    }


def test_parse_runtime_error():
    data = {"lighthouseResult": {"runtimeError": {"code": "ERRORED_DOCUMENT_REQUEST"}, "categories": {
        "performance": {"score": None},
    }}}
    assert lighthouse.parse(data)["error"] == "ERRORED_DOCUMENT_REQUEST"
    assert lighthouse.parse({})["error"] == "no_scores"
