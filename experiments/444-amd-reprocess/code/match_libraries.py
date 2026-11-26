"""Issue #511, Part 2 step 2: compare the Pi's installed library versions against this box's, for
the packages the Reprocess method actually uses (Python, numpy, Pillow, OpenCV, libjpeg). Prints
every difference and why (a PyPI wheel exists vs. a system package is a last resort). Does not
install anything; it only reports, so the choice of what to do about a mismatch stays a human
decision.

Inputs, once Aaron has copied them from the Pi (issue #511, Part 1):
  - /var/lib/dpkg/status                                            (Debian package versions)
  - a list of */dist-info folder names under the Pi's venv site-packages, one per line
  - pyvenv.cfg from that venv (its `version` line gives the Python the venv was built with)

Usage:
  match_libraries.py <pi_dpkg_status> <pi_dist_info_list.txt> <pi_pyvenv.cfg> <this_venv_dir>
"""

import re
import subprocess
import sys
from pathlib import Path

WATCH_DPKG = ["python3", "libjpeg-turbo8", "libjpeg8", "libjpeg62-turbo"]
WATCH_PYPI = ["numpy", "pillow", "opencv-python-headless", "opencv-python", "opencv-contrib-python"]


def parse_dpkg_status(path: Path) -> dict[str, str]:
    versions: dict[str, str] = {}
    name = None
    for line in path.read_text(errors="replace").splitlines():
        if line.startswith("Package: "):
            name = line.removeprefix("Package: ").strip()
        elif line.startswith("Version: ") and name:
            versions[name] = line.removeprefix("Version: ").strip()
            name = None
    return versions


def this_box_dpkg_versions(packages: list[str]) -> dict[str, str]:
    out = {}
    for pkg in packages:
        result = subprocess.run(
            ["dpkg-query", "-W", "-f=${Version}", pkg], capture_output=True, text=True
        )
        if result.returncode == 0:
            out[pkg] = result.stdout.strip()
    return out


_DIST_INFO = re.compile(r"^(?P<name>.+)-(?P<version>[^-]+)\.dist-info$")


def parse_dist_info_list(path: Path) -> dict[str, str]:
    versions: dict[str, str] = {}
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        match = _DIST_INFO.match(Path(line).name)
        if match:
            versions[match.group("name").lower().replace("_", "-")] = match.group("version")
    return versions


def this_venv_dist_info(venv_dir: Path) -> dict[str, str]:
    site_packages = list(venv_dir.glob("lib/python3.*/site-packages"))
    if not site_packages:
        raise SystemExit(f"no site-packages under {venv_dir}")
    versions: dict[str, str] = {}
    for entry in site_packages[0].glob("*.dist-info"):
        match = _DIST_INFO.match(entry.name)
        if match:
            versions[match.group("name").lower().replace("_", "-")] = match.group("version")
    return versions


def read_pyvenv_python(path: Path) -> str | None:
    for line in path.read_text(errors="replace").splitlines():
        if line.lower().startswith("version"):
            return line.split("=", 1)[1].strip()
    return None


def main() -> int:
    pi_dpkg, pi_dist_info, pi_pyvenv, venv_dir = (Path(p) for p in sys.argv[1:5])

    pi_dpkg_versions = parse_dpkg_status(pi_dpkg)
    this_dpkg_versions = this_box_dpkg_versions(WATCH_DPKG)
    pi_pypi_versions = parse_dist_info_list(pi_dist_info)
    this_pypi_versions = this_venv_dist_info(venv_dir)
    pi_python = read_pyvenv_python(pi_pyvenv)
    this_python = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    print(f"Python (venv): Pi {pi_python}  |  this box {this_python}" +
          ("  MATCH" if pi_python == this_python else "  DIFFERENT"))
    print()

    print("-- Debian packages (apt/dpkg) --")
    for pkg in WATCH_DPKG:
        pi_v = pi_dpkg_versions.get(pkg)
        here_v = this_dpkg_versions.get(pkg)
        if pi_v is None and here_v is None:
            continue
        flag = "MATCH" if pi_v == here_v else "DIFFERENT"
        print(f"  {pkg:<22} Pi {pi_v or '(absent)':<20} this box {here_v or '(absent)':<20} {flag}")
    print()

    print("-- Python packages (PyPI wheels, from dist-info) --")
    for pkg in WATCH_PYPI:
        pi_v = pi_pypi_versions.get(pkg)
        here_v = this_pypi_versions.get(pkg)
        if pi_v is None and here_v is None:
            continue
        flag = "MATCH" if pi_v == here_v else "DIFFERENT"
        print(f"  {pkg:<28} Pi {pi_v or '(absent)':<14} this box {here_v or '(absent)':<14} {flag}")
        if pi_v and pi_v != here_v:
            print(f"      -> try: uv pip install --python {venv_dir}/bin/python {pkg}=={pi_v}"
                  " (if an x86_64 wheel exists at that version; otherwise a newer compatible"
                  " wheel is a documented difference, not a silent one)")
    print()
    print("Any DIFFERENT line above is written into docs/metrology-log.md section 41 as a")
    print("documented difference (issue #511, Part 2 step 2), with why: an x86_64 wheel at the")
    print("Pi's exact version, a newer compatible wheel, or a system package as a last resort.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
