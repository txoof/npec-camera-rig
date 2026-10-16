"""The app never uses the research scripts in `experiments/`.

Experiment scripts may import `npec_rig`; nothing under `src/` may import them back, so the
folder can stay out of a deployed rig (`.gitattributes` leaves it out of release archives).
"""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SRC = Path(__file__).resolve().parents[1] / "src"


def _experiment_imports(source: str) -> list[str]:
    """Absolute imports whose top-level package is `experiments` (relative ones are the app's own)."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name.split(".")[0] == "experiments"]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module.split(".")[0] == "experiments":
                found.append(node.module)
    return found


def test_finds_an_experiments_import():
    assert _experiment_imports("import experiments.round1.run_analysis") == [
        "experiments.round1.run_analysis"
    ]
    assert _experiment_imports("from experiments.round1 import x") == ["experiments.round1"]


def test_ignores_the_apps_own_experiments_routes():
    assert _experiment_imports("from npec_rig.routes import experiments") == []
    assert _experiment_imports("from .experiments import router") == []


def test_src_never_imports_experiments():
    offenders = {
        str(p.relative_to(SRC)): names
        for p in sorted(SRC.rglob("*.py"))
        if (names := _experiment_imports(p.read_text()))
    }
    assert offenders == {}
