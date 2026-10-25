#!/bin/sh
set -eu
test "$(pwd)" = "/home/lhj/lhjwork/eda2026"
test ! -e build/exp203/exact-labels.csv
test ! -e build/exp203/regression-labels.csv
test ! -e build/exp203/features.csv

python3 - <<'PY'
import hashlib, json
from pathlib import Path
root = Path.cwd()
frozen = json.load(open("validation/results/exp203-frozen.json"))
sample = json.load(open("validation/results/exp203-sample-freeze.json"))
assert sample["freeze"]["sha256"] == hashlib.sha256(
    Path("validation/results/exp203-frozen.json").read_bytes()).hexdigest()
verified = []
for item in frozen["identities"]:
    relative = Path(item["path"]).relative_to("/home/lhjysyx/EDA2026")
    needed = (str(relative).startswith(("build/exp158/", "doc/", "src/")) or
              str(relative) in ("tests/exp203_exact_labels.cpp", "build/exp155/orbit.i16",
              "validation/results/exp154-frozen-rows.csv", "build/exp203/selector_features.cpp",
              "build/exp203/exp201_ablation.cpp", "build/exp202/manifest.tsv",
              "validation/results/exp202-frozen.json"))
    if needed:
        path = root / relative
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == item["sha256"], str(relative)
        verified.append({"path": str(relative), "sha256": digest})
for item in sample["files"]:
    relative = Path(item["path"]).relative_to("/home/lhjysyx/EDA2026")
    if str(relative) in ("build/exp203/feature-input.csv", "build/exp203/label-requests.csv"):
        assert hashlib.sha256((root / relative).read_bytes()).hexdigest() == item["sha256"]
Path("build/exp203/remote-input-check.json").write_text(json.dumps(verified, indent=2) + "\n")
for item in json.load(open("validation/results/exp202-frozen.json"))["identities"]:
    relative = Path(item["path"]).relative_to("/home/lhjysyx/EDA2026")
    if str(relative).startswith("build/exp171/raw/"):
        assert hashlib.sha256((root / relative).read_bytes()).hexdigest() == item["sha256"]
print("EXP203_INPUT_CHECK_DONE", flush=True)
PY

# Linux UAPI assigns 25; the remote glibc headers omit this newer advice.
g++ -std=c++17 -O2 -Wall -Wextra -Wno-unused-parameter -DMADV_COLLAPSE=25 \
  -o build/exp203/exact_labels tests/exp203_exact_labels.cpp \
  build/exp158/src/architecture.cpp build/exp158/src/router.cpp \
  build/exp158/src/residue_estimator.cpp
g++ -std=c++17 -O2 -Wall -Wextra -Wno-unused-parameter -Isrc \
  -o build/exp203/selector_features build/exp203/selector_features.cpp src/architecture.cpp

/usr/bin/time -v -o build/exp203/regression.time timeout 900 taskset -c 3 \
  build/exp203/exact_labels doc/eda比赛文件/arch validation/results/exp154-frozen-rows.csv \
  build/exp155/orbit.i16 build/exp203/regression-labels.csv \
  >build/exp203/regression.stdout 2>build/exp203/regression.stderr
printf 'EXP203_REGRESSION_DONE\n'
/usr/bin/time -v -o build/exp203/labels.time timeout 900 taskset -c 3 \
  build/exp203/exact_labels doc/eda比赛文件/arch build/exp203/label-requests.csv \
  build/exp155/orbit.i16 build/exp203/exact-labels.csv \
  >build/exp203/labels.stdout 2>build/exp203/labels.stderr
printf 'EXP203_LABELS_DONE\n'
/usr/bin/time -v -o build/exp203/control.time timeout 600 taskset -c 3 \
  build/exp203/selector_features doc/eda比赛文件/arch validation/results/exp174-predictions.csv \
  build/exp202/manifest.tsv build/exp203/control-features.csv \
  >build/exp203/control.stdout 2>build/exp203/control.stderr
/usr/bin/time -v -o build/exp203/features.time timeout 600 taskset -c 3 \
  build/exp203/selector_features doc/eda比赛文件/arch build/exp203/feature-input.csv \
  build/exp202/manifest.tsv build/exp203/features.csv \
  >build/exp203/features.stdout 2>build/exp203/features.stderr

python3 - <<'PY'
import csv, hashlib, json, re, subprocess
from pathlib import Path
def identity(path):
    p = Path(path)
    return {"path": str(p), "bytes": p.stat().st_size,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
record = {"experiment": 203, "machine": "r9r4900", "cwd": str(Path.cwd()),
          "compiler": subprocess.check_output(["g++", "--version"], text=True).splitlines()[0],
          "runner": identity("validation/exp203_remote.sh"), "resources": {}}
for stage in ("regression", "labels", "control", "features"):
    prefix = Path("build/exp203") / stage
    timing = prefix.with_suffix(".time").read_text()
    rss = int(re.search(r"Maximum resident set size \(kbytes\): (\d+)", timing)[1]) * 1024
    cpu = sum(float(re.search(pattern, timing)[1]) for pattern in
        (r"User time \(seconds\): ([\d.]+)", r"System time \(seconds\): ([\d.]+)"))
    assert rss <= 2_000_000_000 and not prefix.with_suffix(".stderr").read_text()
    record["resources"][stage] = {"cpu_s": cpu, "rss_bytes": rss,
                                 "time": identity(prefix.with_suffix(".time"))}
for name in ("regression", "labels"):
    text = Path(f"build/exp203/{name}.stdout").read_text()
    assert "threads=1" in text and "labels_done" in text
assert "known_checks=6176" in Path("build/exp203/regression.stdout").read_text()
assert "span_checks=8" in Path("build/exp203/labels.stdout").read_text()
old = list(csv.DictReader(open("build/exp202/features.csv")))
control = list(csv.DictReader(open("build/exp203/control-features.csv")))
assert len(old) == len(control) == 6176
for a, b in zip(old, control):
    assert all(a[k] == b[k] for k in a if k not in ("exact", "index"))
record["files"] = [identity("build/exp203/" + name) for name in
    ("exact_labels", "selector_features", "regression-labels.csv", "exact-labels.csv",
     "features.csv", "control-features.csv", "remote-input-check.json")]
record["all_passed"] = True
Path("build/exp203/remote-run.json").write_text(json.dumps(record, indent=2) + "\n")
print("EXP203_REMOTE_DONE", flush=True)
PY
