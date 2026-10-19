"""Run every check SDM has and print one summary (M10).

    uv run python scripts/check_all.py            # lint, format, Python tests, extension tests
    uv run python scripts/check_all.py --chrome   # also: does the real Chrome find SDM's host?
    uv run python scripts/check_all.py --runs 5   # run the Python tests 5 times (flakiness)

Exits with 0 only if everything passed.
"""

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(name: str, command: list[str], cwd: Path = ROOT) -> tuple[str, bool, float, str]:
    print(f"--- {name}: {' '.join(command)}", flush=True)
    started = time.perf_counter()
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)  # noqa: S603
    seconds = time.perf_counter() - started
    output = (result.stdout + result.stderr).strip()
    tail = "\n".join(output.splitlines()[-3:])
    print(tail, flush=True)
    return name, result.returncode == 0, seconds, tail.splitlines()[-1] if tail else ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--chrome", action="store_true", help="also check the real Chrome")
    parser.add_argument("--runs", type=int, default=1, help="run the Python tests N times")
    args = parser.parse_args()

    python = sys.executable
    results = [
        run("ruff check", [python, "-m", "ruff", "check", "."]),
        run("ruff format", [python, "-m", "ruff", "format", "--check", "."]),
    ]
    for number in range(1, args.runs + 1):
        label = "pytest" if args.runs == 1 else f"pytest run {number} of {args.runs}"
        results.append(run(label, [python, "-m", "pytest", "-q", "-p", "no:cacheprovider"]))
    node = shutil.which("node")
    if node:
        results.append(run("extension tests", [node, "--test"], cwd=ROOT / "extension"))
    else:
        results.append(("extension tests", False, 0.0, "Node.js not found"))
    if args.chrome:
        script = str(ROOT / "scripts" / "chrome_bridge_check" / "check.mjs")
        results.append(run("real Chrome check", [node or "node", script]))

    print("\n=== Summary")
    for name, ok, seconds, last in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name:<22} {seconds:6.1f} s  {last}")
    passed = all(ok for _, ok, _, _ in results)
    print("\nAll checks passed." if passed else "\nSome checks FAILED (see above).")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
