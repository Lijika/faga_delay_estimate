#!/usr/bin/env python3
"""Check complete saved real-map diagnosis evidence without running the model."""
import ast
import hashlib
import json
import math
from pathlib import Path

ROOT, LAUNCH = Path("validation/results/exp535"), Path("validation/results/exp535-launch")
read = lambda path: json.loads(Path(path).read_text())


def same(path, row):
    raw = Path(path).read_bytes()
    assert (len(raw), hashlib.sha256(raw).hexdigest()) == (row["bytes"], row["sha256"]), str(path)


received = read(LAUNCH / "received.json")
assert received["transfer"]["exit_code"] == 0 and not received["transfer"]["stderr"]
for row in received["files"]:
    same(row["path"], row)
frozen, report, inputs = [read(ROOT / (name + ".json")) for name in ("freeze", "report", "input")]
assert report["all_passed"] and report["complete_port_validation"]
assert not report["production_cpu_validated"] and not report["independent_holdout_validated"]
assert frozen["new_labels"] == frozen["new_training"] == 0 and frozen["threads"] == 1
assert report["host"] == frozen["host"] == "lhj-R4900-G3"
assert (report["rows"], report["sources"], report["targets"], report["pairs"]) == (1000000, 208, 288, 59904)
assert inputs["rows"] == inputs["unique_rows"] == 1000000
assert inputs["pairs"] == 59904 and inputs["min_pair_rows"] > 0
assert report["new_asset_bytes"] <= 500000000
oracle, model = read(ROOT / "oracle.json"), read(ROOT / "model.json")
assert oracle["complete"] and model["complete"] and model["predictions_checked"] == 2000000
assert len(oracle["sources"]) == 208 and sum(r["rows"] for r in oracle["sources"]) == 1000000
fields = read("validation/results/exp500-preparation/fields.json")
for s, row in enumerate(oracle["sources"]):
    assert row["source"] == s and row["complete_raw_sha_checked"] and row["rows"] > 0
    assert (row["asset"]["bytes"], row["asset"]["sha256"]) == \
           (fields[s]["asset"]["bytes"], fields[s]["asset"]["sha256"])
assert oracle["output"]["bytes"] == model["output"]["bytes"] == 8000000
assert inputs["queries"]["bytes"] == 40000012
assert model["threads"] == 1 and read(ROOT / "build.json")["exit_code"] == 0
run, metrics = read(ROOT / "query-run.json"), read(ROOT / "query.stderr")
assert run["exit_code"] == 0 and run["threads"] == 1
assert run["rss_bytes"] <= 2000000000 and run["wall_s"] <= 3600
assert metrics["rows"] == 1000000 and metrics["predictions"] == 2000000
assert metrics["table_bytes"] == 735510528
assert not (ROOT / "query.stdout").read_bytes()
baseline = read("validation/results/exp506/report.json")
assert abs(report["statistics"]["exp354"]["accuracy_pp"] - baseline["metrics"]["accuracy_all"]) < 1e-9
for decomposition in report["decomposition"]:
    assert decomposition["total_squared_ps"] == decomposition["geometry_squared_ps"] + \
           decomposition["representation_squared_ps"] + decomposition["cross_squared_ps"]
for prefix in {name.split("/", 1)[0] for name in report["groups"]}:
    groups = [value for name, value in report["groups"].items() if name.startswith(prefix + "/")]
    for arm in frozen["arms"]:
        assert sum(g[arm]["rows"] for g in groups) == 1000000
        assert math.isclose(sum(g[arm]["rows"] * g[arm]["accuracy_pp"] for g in groups) / 1000000,
                            report["statistics"][arm]["accuracy_pp"], rel_tol=0, abs_tol=1e-9)
    for mode in range(2):
        for key in ("geometry_squared_ps", "representation_squared_ps", "cross_squared_ps", "total_squared_ps"):
            assert sum(g["decomposition"][mode][key] for g in groups) == report["decomposition"][mode][key]
g, r = report["decomposition"][0], report["statistics"]
pair = report["paired_oracle_coordinate"]
assert pair["clusters"] == inputs["clusters"] and pair["draws"] == 2000 and pair["seed"] == 20261020535
assert pair["unit"] == "complete source pin" and pair["ci95_pp"][0] <= pair["ci95_pp"][1]
assert abs(pair["delta_pp"] - (r["oracle_compressed"]["accuracy_pp"] - r["oracle_original"]["accuracy_pp"])) < 1e-9
assert report["hypotheses"] == dict(
    geometry_dominant=r["oracle_original"]["accuracy_pp"] < 99.25 and
    g["geometry_squared_ps"] >= 2 * g["representation_squared_ps"],
    coordinate_sufficient=report["geometry_squared_reduction"] >= .2 and
    pair["delta_pp"] >= .05 and pair["ci95_pp"][0] > 0)
for row in frozen["files"]:
    path = row["path"]
    if path.startswith("experiment/"):
        original = ROOT / "protocol-original.md"
        same(original, row)
        assert Path(path).read_bytes().startswith(original.read_bytes())
        continue
    for prefix in ("../exp532/", "../exp534/"):
        if path.startswith(prefix):
            path = path[len(prefix):]
    same(path, row)
for row in read(LAUNCH / "workspace-before.json")["protected_files"]:
    same(row["path"], row)
assert read(LAUNCH / "remote/evaluate.run.json")["exit_code"] == 0
assert not (LAUNCH / "remote/evaluate.stderr").read_bytes()
for path in ("validation/exp535_real_map.py", "validation/exp535_evidence_check.py",
             str(LAUNCH / "driver.py"), str(LAUNCH / "collect.py")):
    ast.parse(Path(path).read_text(), filename=path)
write_path = ROOT / "local-audit.json"
write_path.write_text(json.dumps(dict(passed=True, complete_port_validation=True,
    protected_files_preserved=True, hypotheses=report["hypotheses"],
    scope="Saved complete development diagnosis; production CPU and independent requests remain unverified."),
    indent=2) + "\n")
print("EXP535_SAVED_COMPLETE_REAL_MAP_DIAGNOSIS_PASSED")
