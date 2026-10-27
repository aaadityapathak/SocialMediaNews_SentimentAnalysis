"""Run each component in a fresh process to isolate Fission import paths."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUITES = {
    "application": ROOT,
    "harvesters": ROOT / "backend/harvesters",
    "processing": ROOT / "backend/processing",
    "api": ROOT / "backend/api",
    "ml": ROOT / "backend/ml-server",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--integration", action="store_true")
    parser.add_argument("--suite", choices=SUITES, action="append")
    args, pytest_args = parser.parse_known_args()
    results = {}
    for name in args.suite or SUITES:
        print(f"\nRunning {name} tests", flush=True)
        command = [sys.executable, "-m", "pytest", "-q", *pytest_args]
        if args.integration:
            command.append("--run-integration")
        env = os.environ.copy()
        env.setdefault("NLTK_DATA", str(ROOT / "nltk_data"))
        results[name] = subprocess.run(
            command, cwd=SUITES[name], env=env, check=False
        ).returncode
    print(
        "\n"
        + ", ".join(
            f"{name}: {'passed' if code == 0 else 'FAILED'}"
            for name, code in results.items()
        )
    )
    return int(any(results.values()))


if __name__ == "__main__":
    raise SystemExit(main())
