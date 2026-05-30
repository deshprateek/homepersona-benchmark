"""
Verify that the cmds_hash in VERSION matches the current command columns across all CSVs.
run.py calls this at startup. Also runnable standalone: python harness/check_version.py
"""
import csv
import hashlib
import pathlib
import sys

BENCHMARK_DIR = pathlib.Path(__file__).parent.parent
VERSION_FILE = BENCHMARK_DIR / "VERSION"


def compute_hash() -> str:
    files = sorted((BENCHMARK_DIR / "data").glob("v0.1_*.csv"))
    if not files:
        print("ERROR: No v0.1_*.csv files found in", BENCHMARK_DIR)
        sys.exit(1)

    commands = []
    for f in files:
        with open(f) as fh:
            for row in csv.DictReader(fh):
                commands.append(row["command"])

    return hashlib.sha256("\n".join(commands).encode()).hexdigest()[:8]


def read_stored_hash() -> tuple[str, str]:
    """Returns (version_string, stored_hash)."""
    version, stored_hash = None, None
    for line in VERSION_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("cmds_hash:"):
            stored_hash = line.split(":", 1)[1].strip()
        else:
            version = line
    if not version or not stored_hash:
        print("ERROR: VERSION file is malformed —", VERSION_FILE)
        sys.exit(1)
    return version, stored_hash


def check() -> tuple[bool, str, str]:
    version, stored_hash = read_stored_hash()
    current_hash = compute_hash()
    return current_hash == stored_hash, version, current_hash


if __name__ == "__main__":
    ok, version, current_hash = check()
    if ok:
        print(f"OK  version={version}  cmds_hash={current_hash}")
    else:
        _, _, stored = read_stored_hash()[1], None, read_stored_hash()[1]
        print(f"MISMATCH  version={version}")
        print(f"  stored:  {read_stored_hash()[1]}")
        print(f"  current: {current_hash}")
        print("Bump VERSION and update cmds_hash before running.")
        sys.exit(1)
