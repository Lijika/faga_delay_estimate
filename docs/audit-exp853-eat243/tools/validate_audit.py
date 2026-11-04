"""Verify audit evidence, arithmetic, links and unchanged source status."""
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
import csv
import hashlib
import json
import math
import re
import subprocess
import zipfile

OUT = Path(__file__).resolve().parents[1]
ROOT = Path("/home/lhjysyx/EDA2026")


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load(rel):
    return json.loads((OUT / rel).read_text())


def main():
    result = {"checked_utc": datetime.now(timezone.utc).isoformat(), "checks": {}}
    checks = result["checks"]
    snap = load("index/snapshot.json")
    rows = list(csv.DictReader((OUT / "index/experiments.csv").open(encoding="utf-8-sig")))
    assert len(rows) == snap["experiments"] == 1018
    with zipfile.ZipFile(OUT / "index/experiment-corpus.zip") as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == len(rows)
        for row in rows:
            p = OUT / "evidence/experiment" / row["filename"]
            assert p.stat().st_size == int(row["bytes"])
            assert sha(p) == row["sha256"]
            assert hashlib.sha256(archive.read("experiment/" + p.name)).hexdigest() == row["sha256"]
    checks["experiment_copies_and_zip"] = len(rows)
    count = 0
    for filename in ("index/copied-evidence.json", "index/additional-evidence.json"):
        for entry in load(filename):
            p = OUT / entry["copy"]
            assert p.stat().st_size == entry["bytes"] and sha(p) == entry["sha256"], str(p)
            count += 1
    checks["evidence_copy_hashes"] = count

    summary = load("evidence/formal243/evidence/summary.json")
    assert len(summary["runs"]) == 14
    actual = {}
    for arm in ("A", "B"):
        runs = [r for r in summary["runs"] if r["label"] == arm]
        timed = [r for r in runs if r["phase"] == "timed"]
        assert len(runs) == 7 and len(timed) == 6
        assert all(r["exit_code"] == 0 and r["threads_observed"] == 1 for r in runs)
        for r in runs:
            assert math.isclose(r["cpu_s"], r["user_s"] + r["sys_s"], abs_tol=1e-9)
        actual[arm] = {"mean_cpu_s": mean(r["cpu_s"] for r in timed),
                       "max_rss_bytes": max(r["rss_bytes"] for r in runs)}
        assert math.isclose(actual[arm]["mean_cpu_s"],
                            summary["timing"][arm]["cpu_s"]["mean"], abs_tol=1e-10)
    assert actual["B"]["mean_cpu_s"] == 125.208939
    assert actual["A"]["max_rss_bytes"] == 309907456
    assert actual["B"]["max_rss_bytes"] == 295555072
    assert len({r["output"]["sha256"] for r in summary["runs"]}) == 1
    gain = (actual["A"]["mean_cpu_s"] - actual["B"]["mean_cpu_s"]) / 120
    assert math.isclose(gain, summary["statistics"]["joint_score_delta_point"], abs_tol=1e-12)
    accuracy = summary["paired_accuracy"]["accuracy_pp"]
    assert accuracy["A"] == accuracy["B"] == 98.85534283747039
    assert summary["paired_accuracy"]["sample_rows"] == 59904 * 64
    checks["formal243_recomputed"] = actual

    formulas = {
        "role_pairs": (208 * 288, 59904),
        "directory_entries": (208 * 288 * 480, 28753920),
        "surface_cells": (12 * 46, 552),
        "directory_planes": (208 * 288 * 480 * 5, 143769600),
        "directory_runtime": (208 * 288 * 480 * 4, 115015680),
        "first": (4 * 2048 * 552 * 2, 9043968),
        "second": (4 * 256 * 552 * 2, 1130496),
        "direct": (33280 * 552 * 2, 36741120),
        "direct_keys": (33280 * 4, 133120),
        "planes_scratch": (138240 * 5, 691200),
        "runtime_arrays": (115015680 + 9043968 + 1130496 + 36741120 + 133120 + 691200,
                           162755584),
        "logical_assets": (143769600 + 9043968 + 1130496 + 36741120 + 133120, 190818304),
        "compressed_assets": (76014929 + 876616 + 70574 + 2303669 + 133120, 79398908),
        "elf_other": (86937624 - 79398908, 7538716),
        "strict_elf_increment": (100000000 - 1 - 86937624, 13062375),
        "rss_headroom": (2000000000 - 295555072, 1704444928),
        "dense_nominal": (208 * 288 * 480 * 552 * 2, 31744327680),
        "one_field": (550 * 120 * 160 * 2, 21120000),
        "field_20_projection": (84562554 + 7989904, 92552458),
        "parent5_stream": (math.ceil(877212320 * 5 / 8) + 40, 548257740),
        "parent5_dict": (160 * 32, 5120),
        "parent5_inverse": (160 * 256, 40960),
        "parent5_full": (548257740 + 5120 + 40960, 548303820),
        "parent5_saving": (877212320 - 548303820, 328908500),
        "parent5_elf_over": (108423824 - 100000000, 8423824),
        "rank64_factor": ((59904 + 264960) * 64 * 2, 41582592),
        "phase_C": (59904 * 480 * 2, 57507840),
        "phase_component": (23403336 + 41582592 + 6000000, 70985928),
        "sum_cartesian": (4 * 2048 * 256 * 552 * 2, 2315255808),
        "sum_actual_pairs": (266255 + 274638 + 287742 + 282532, 1111167),
        "sum_table": (1111167 * 552 * 2, 1226728368),
        "sum_memory_screen": (269049856 + 1226728368 + 8388608 + 67108864, 1571275696),
        "exp842_pairs": (417978 + 443537 + 436286 + 426008, 1723809),
        "exp842_runtime": (1723809 * 552 * 2, 1903085136),
        "exp842_rss_additive": (1903085136 + 270217216, 2173302352),
        "exp842_elf_projection": (
            90509336 + math.ceil(2630028 * 1723809 / 17927) + 8388608 + 262144, 352056052),
        "directory_29_bits": (math.ceil(28753920 * 29 / 8), 104232960),
        "r8_d4_payload": (8 * ((2**4 - 1) * 4 + 2**4 * 4), 992),
        "eat181_node_dtype": (7808 * (8 + 4 + 8 + 8 + 1 + 4 + 4 + 8 + 4 + 1 + 1 + 1 + 4), 437248),
        "eat181_offsets": (120 * 8, 960),
        "oneb_io_bytes": (35197849579 + 40135575559, 75333425138),
    }
    for name, (computed, expected) in formulas.items():
        assert computed == expected, (name, computed, expected)
    assert load("evidence/selected-results/exp842/construction.json")["projected_elf_bytes"]["AB"] == formulas["exp842_elf_projection"][0]
    init = max(0, (100 * .52224 - 10.62562) / 99)
    projection = init + 10 * (10.62562 - init)
    admission = load("evidence/formal243/evidence/cpu-admission.json")
    assert math.isclose(projection, admission["projected_complete1b_cpu_s"], abs_tol=1e-10)
    checks["integer_formulas"] = {k: v[0] for k, v in formulas.items()}
    checks["cpu_admission_recomputed_s"] = projection
    terminal = load("evidence/eat181-terminal/main-review.json")
    assert terminal["completed_all_runs"] == 12 and terminal["planned_runs"] == 14
    assert terminal["timed_descriptive"]["B"]["completed_timed_runs"] == 5
    assert math.isclose(mean(terminal["timed_descriptive"]["B"]["cpu_s"]), 1703.2995142)
    checks["eat181_partial_protocol"] = "12 completed / 14 planned; 5 timed per arm"

    authored = sorted(OUT.glob("[0-9][0-9]-*.md")) + sorted((OUT / "theory").glob("*.md"))
    link_count = 0
    prohibited = []
    for p in authored:
        text = p.read_text()
        assert "cite" not in text and "turn263" not in text
        assert text.count("```") % 2 == 0, f"unbalanced fence: {p}"
        for token in ("显著提升", "大幅提升", "底层逻辑", "赋能", "闭环", "兜底", "收口", "压实"):
            if token in text:
                prohibited.append((p.name, token))
        for target in re.findall(r"(?<!!)\[[^\]\n]+\]\(([^)\n]+)\)", text):
            if re.match(r"^[a-z]+://", target) or target.startswith("#"):
                continue
            target = target.split("#")[0].strip("<>")
            if target in ("delivery-manifest.json", "index/verification.json"):
                continue  # These receipts are written after successful checks.
            resolved = (p.parent / target).resolve()
            assert resolved.exists(), f"broken link in {p.name}: {target}"
            link_count += 1
    assert not prohibited, prohibited
    checks["authored_markdown_files"] = len(authored)
    checks["authored_relative_links"] = link_count
    if ROOT.is_dir() and (ROOT / ".git").exists():
        status = subprocess.check_output(["git", "status", "--porcelain=v1", "-uall"],
                                         cwd=ROOT, text=True)
        assert status == (OUT / "index/git-status-before.txt").read_text()
        assert sha(ROOT / "estimate") == snap["root_estimate"]["sha256"]
        checks["original_git_status_and_root_elf_unchanged"] = True
    else:
        checks["original_git_status_and_root_elf_unchanged"] = "not available on this machine"
    result["passed"] = True
    result["not_performed"] = ["algorithm execution", "new exact labels", "full result corpus re-scoring",
                               "official platform verification", "full release rebuild"]
    (OUT / "index/verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"passed": True, "experiments": len(rows), "evidence_copies": count,
                      "integer_formulas": len(formulas), "authored_links": link_count},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
