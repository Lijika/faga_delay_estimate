#!/usr/bin/env python3
"""Replay accepted compiler argv using packaged source/assets in an explicit scratch directory."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


def commands(root, out, report):
    original = Path(report["cwd"]).parent
    translated = {}
    for command in report["commands"]:
        output = command[command.index("-o") + 1]
        translated[output] = str(out / ("estimate" if command is report["commands"][-1]
                                        else f"object-{len(translated)}.o"))
    def path(argument):
        if argument in translated:
            return translated[argument]
        if argument.startswith(str(original / "build/overlay") + "/"):
            return str(root / "source" / Path(argument).relative_to(original / "build/overlay"))
        if argument.startswith(str(original / "source") + "/"):
            return str(root / "source" / Path(argument).relative_to(original / "source"))
        if argument == str(original / "build/assets.S"):
            return str(out / "assets.S")
        return argument
    return [[path(argument) for argument in command] for command in report["commands"]]


def assembly(root):
    original = (root / "evidence/original-assets.S").read_text()
    for symbol in ("direct_exact", "direct_keys", "directory212", "first212", "second212"):
        pattern = rf'({symbol}_begin:\n)\.incbin "[^"]+"'
        original, count = re.subn(pattern, lambda m: m[1] + ".incbin " +
                                  json.dumps(str(root / "assets" / symbol)), original)
        if count != 1:
            raise RuntimeError("accepted assembly symbol missing: " + symbol)
    return original


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    root, out = args.package.resolve(), args.out.resolve()
    report = json.loads((root / "evidence/build-report.json").read_text())
    argv = commands(root, out, report)
    if args.plan_only:
        print(json.dumps({"commands": argv, "assembly": assembly(root)}, indent=2))
        return
    out.mkdir(parents=True, exist_ok=False)
    (out / "tmp").mkdir()
    (out / "assets.S").write_text(assembly(root))
    env = dict(os.environ, TMPDIR=str(out / "tmp"))
    with (out / "build.log").open("x") as log:
        for command in argv:
            log.write(json.dumps(command) + "\n")
            log.flush()
            subprocess.run(command, cwd=root / "source", env=env,
                           stdout=log, stderr=log, check=True, timeout=180)
    digest = hashlib.sha256()
    with (out / "estimate").open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    binary = {"bytes": (out / "estimate").stat().st_size, "sha256": digest.hexdigest()}
    (out / "rebuild-result.json").write_text(json.dumps({"binary": binary, "commands": argv}, indent=2) + "\n")
    if binary != report["binary"]:
        raise RuntimeError("rebuilt ELF differs; retained actual result and build.log")
    print(json.dumps({"passed": True, "binary": binary}))


if __name__ == "__main__":
    main()
