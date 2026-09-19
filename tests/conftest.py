import os
import tempfile

os.environ.setdefault("NPEC_RIG_CAPTURES_DIR", tempfile.mkdtemp(prefix="npec-rig-tests-"))
