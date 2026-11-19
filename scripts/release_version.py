"""pyproject.toml의 설치판 버전을 읽고 태그와 일치를 검사한다 (Python 3.11+)."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
import tomllib


def version_tuple(text: str) -> tuple[int, int, int]:
    if not isinstance(text, str) or not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", text):
        raise ValueError("project.version must be a stable X.Y.Z version")
    parts = tuple(map(int, text.split(".")))
    if any(part > 65534 for part in parts):
        raise ValueError("version components must be between 0 and 65534")
    return parts


def read_version(path: Path) -> str:
    with path.open("rb") as file:
        version = tomllib.load(file)["project"]["version"]
    version_tuple(version)
    return version


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pyproject", type=Path, default=Path(__file__).resolve().parents[1] / "pyproject.toml")
    parser.add_argument("--check-tag")
    args = parser.parse_args()
    try:
        version = read_version(args.pyproject)
        if args.check_tag is not None and args.check_tag != f"v{version}":
            raise ValueError("tag does not match project.version")
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f"release version error: {exc}", file=sys.stderr)
        return 1
    print(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
