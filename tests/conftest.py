import os
import tempfile

import pytest

os.environ.setdefault("NPEC_RIG_CAPTURES_DIR", tempfile.mkdtemp(prefix="npec-rig-tests-"))


@pytest.fixture(autouse=True)
def isolated_settings_db(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    # A fresh DB per test — CameraManager loads persisted settings on construction, so sharing
    # one DB across tests would leak state between them.
    monkeypatch.setenv("NPEC_RIG_DB_PATH", str(tmp_path / "rig.db"))
