"""Verify pinned wheels and unpack them without executing install hooks."""

import argparse
import hashlib
import re
import zipfile
from pathlib import Path


REQUIREMENT = re.compile(
    r"^(?P<name>[A-Za-z0-9_.-]+)==(?P<version>[^\s]+)\s+"
    r"--hash=sha256:(?P<digest>[0-9a-f]{64})$"
)


def normalize(value):
    return re.sub(r"[-_.]+", "-", value).lower()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel-dir", required=True)
    parser.add_argument("--requirements", required=True)
    parser.add_argument("--target", required=True)
    args = parser.parse_args()

    wheel_dir = Path(args.wheel_dir)
    target = Path(args.target)
    requirements = {}
    for raw_line in Path(args.requirements).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = REQUIREMENT.fullmatch(line)
        if match is None:
            raise SystemExit(f"invalid requirement line: {line}")
        key = (normalize(match.group("name")), match.group("version"))
        requirements[key] = match.group("digest")

    selected = {}
    for wheel in sorted(wheel_dir.glob("*.whl")):
        parts = wheel.stem.split("-")
        if len(parts) < 5:
            continue
        distribution, version = parts[0], parts[1]
        key = (normalize(distribution), version)
        if key in requirements:
            selected[key] = wheel

    missing = sorted(set(requirements) - set(selected))
    if missing:
        raise SystemExit(f"missing wheels: {missing}")

    target.mkdir(parents=True, exist_ok=True)
    for key, wheel in selected.items():
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        if digest != requirements[key]:
            raise SystemExit(f"wheel hash mismatch: {wheel.name}")
        with zipfile.ZipFile(wheel) as archive:
            for member in archive.infolist():
                relative = Path(member.filename)
                if relative.is_absolute() or ".." in relative.parts:
                    raise SystemExit(f"unsafe wheel member: {member.filename}")
                archive.extract(member, target)


if __name__ == "__main__":
    main()
