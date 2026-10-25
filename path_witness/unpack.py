#!/usr/bin/env python3
"""Verify archived identities and unpack the frozen binary inputs."""
import gzip
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent


def identity(path):
    path = Path(path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return dict(path=str(path), bytes=path.stat().st_size, sha256=digest.hexdigest())


def unpack(directory):
    directory.mkdir(parents=True, exist_ok=True)
    for record in json.loads((HERE / "manifest.json").read_text()):
        source = HERE.parent / record["published"]
        if record["compressed"]:
            target = directory / source.relative_to(HERE).with_suffix("")
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                with gzip.open(source, "rb") as stream, target.open("xb") as out:
                    for block in iter(lambda: stream.read(1 << 20), b""):
                        out.write(block)
        else:
            target = source
        actual = identity(target)
        assert all(actual[k] == record[k] for k in ("bytes", "sha256")), target


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: unpack.py WORK_DIRECTORY")
    unpack(Path(sys.argv[1]).resolve())
    print("Frozen archive identities verified.")
