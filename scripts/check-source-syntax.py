"""Offline syntax coverage for tracked runtime, harness and test sources.

This parses source text only: it never imports Python modules, runs shell
commands from the files, or evaluates JavaScript. It is not a logic proof.
"""

import json
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFIXES = ("apps/", "packages/", "scripts/", "infrastructure/", "tests/", "evals/")


def main():
    names = (
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
        )
        .decode()
        .split("\0")
    )
    counts = Counter()
    for name in sorted(set(names)):
        path = ROOT / name
        if not name.startswith(PREFIXES) or not path.is_file():
            continue
        suffix = path.suffix
        if suffix == ".py":
            compile(path.read_bytes(), name, "exec", dont_inherit=True)
        elif suffix in {".mjs", ".cjs"}:
            subprocess.run(["node", "--check", str(path)], check=True, cwd=ROOT)
        elif suffix == ".sh":
            subprocess.run(["bash", "-n", str(path)], check=True, cwd=ROOT)
        elif suffix == ".json":
            json.loads(path.read_text())
        else:
            continue
        counts[suffix] += 1
    print(json.dumps({"syntax_only": True, "files": dict(counts), "passed": True}))


if __name__ == "__main__":
    main()
