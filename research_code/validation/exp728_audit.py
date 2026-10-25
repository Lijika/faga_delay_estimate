#!/usr/bin/env python3
"""Reconcile raw runs, complete-output identity, and reused exact evidence."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path("../exp709/validation").resolve()))
from exp709_cost_skeleton import check, identity, read, write

ROOT = Path("validation/results/exp728")


def same_bytes(a, b):
    assert all(a[k] == b[k] for k in ("bytes", "sha256"))


def main():
    report, frozen = (read(ROOT/n) for n in ("1b-report.json", "1b-freeze.json"))
    old = Path("../exp722/validation/results/exp722")
    previous, decision, score = (read(old/n) for n in
                                ("1b-report.json", "1b-decision.json", "score-1b/accuracy.json"))
    check(old/"1b-report.json", frozen["previous_report"])
    check(old/"score-1b/accuracy.json", frozen["previous_score"])
    check(old/"1b-report.json", decision["report"])
    check(old/"score-1b/accuracy.json", decision["score"])
    prior_audit = read(old/"close-audit.json")
    assert prior_audit["all_checks_passed"] and prior_audit["quality_gate"]
    for item in prior_audit["files"]:
        check(Path("../exp722")/item["path"], item)
    assert decision["quality_gate"] and report["all_checks_passed"]
    assert report["rows"] == report["unique_rows"] == 1_000_000_000
    assert report["port_pairs"] == 59904 and report["exact_sample_rows"] == 3_833_856
    same_bytes(report["binary"], frozen["binary"])
    check(report["binary"]["path"], report["binary"])
    assert report["binary"]["bytes"] < 100_000_000
    assert report["input"] == frozen["input"] == previous["input"]
    same_bytes(report["output"], previous["output"])
    same_bytes(report["output"], frozen["expected_output"])
    assert report["complete_output_identical"]
    assert report["contract_reused"] == previous["contract"]
    assert previous["contract"]["contract_passed"] and previous["contract"]["rows"] == report["rows"]
    assert report["score_reused"] == decision["score"]
    assert score["evidence"]["C"]["source_output"] == previous["output"]
    assert report["accuracy"] == decision["accuracy"] == score["accuracy"]["C"]
    for key, value in report["accuracy"].items():
        expected = prior_audit["estimates"]["C"][key]
        pairs = zip(value, expected) if isinstance(value, list) else [(value, expected)]
        assert all(abs(a-b) < 1e-9 for a, b in pairs)
    assert report["accuracy_delta_pp"] == report["new_exact_rows"] == 0
    for stem, count in (("empty-100m", 100_000_000), ("1b", 1_000_000_000)):
        raw = read(ROOT/(stem+".run.json"))
        assert raw["exit_code"] == 0 and raw["threads"] == 1
        assert raw["rss_bytes"] <= 2_000_000_000 and raw["wall_s"] <= 3600
        assert abs(raw["cpu_s"]-raw["user_s"]-raw["sys_s"]) < 1e-10
        assert read(ROOT/(stem+".stderr")) == dict(rows=count, unreachable=0, query_allocations=0)
        recorded = report["run"] if stem == "1b" else read(ROOT/"package-check.json")["run"]
        assert raw == recorded
    cpu_report = Path("../exp725/validation/results/exp725/1b-report.json")
    check(cpu_report, frozen["previous_cpu_report"])
    cpu_baseline = read(cpu_report)
    assert read(cpu_report.parent/"independent-audit.json")["all_checks_passed"]
    assert cpu_baseline["input"] == report["input"]
    same_bytes(cpu_baseline["output"], report["output"])
    assert report["baseline_run"] == cpu_baseline["run"]
    saved = cpu_baseline["run"]["cpu_s"]-report["run"]["cpu_s"]
    assert saved == report["historical_cpu_saved_s"]
    assert report["baseline_cpu_historical"] and report["one_candidate_run"]
    assert report["cpu_200s_goal"] == (report["run"]["cpu_s"] < 200)
    assert report["cpu_100s_goal"] == (report["run"]["cpu_s"] <= 100)
    assert not report["final_accuracy_above_99_verified"] and not report["platform_verified"]
    cleanup, retention = (read(ROOT/n) for n in ("1b-cleanup.json", "retention-complete.json"))
    retained = read(old/"exp722-1b-retained.json")
    assert retained == frozen["retained"] == cleanup["retained"]
    assert retained["full_roundtrip_passed"] and cleanup["complete_roundtrip_evidence_reused"]
    same_bytes(retained["original"], retained["restored"])
    same_bytes(retained["original"], report["output"])
    same_bytes(cleanup["archive"], retained["archive"])
    archive = Path(cleanup["archive"]["path"])
    assert archive.is_file() and archive.stat().st_size == cleanup["archive"]["bytes"]
    assert cleanup["file"] == report["output"]
    assert retention["all_checks_passed"] and retention["released_bytes"] == report["output"]["bytes"]
    assert retention["deleted"] == report["output"]["path"] and not Path(retention["deleted"]).exists()
    clean = read(ROOT/"package-check.json")
    assert clean["all_passed"] and clean["static_linked"] and clean["empty_environment"]
    same_bytes(clean["binary"], report["binary"])
    assert read(ROOT/"stage-publication.json")["bin_sha256"] == report["binary"]["sha256"]
    result = dict(all_checks_passed=True, cpu_s=report["run"]["cpu_s"],
        historical_cpu_saved_s=saved, accuracy=report["accuracy"], exact_sample_rows=3_833_856,
        accuracy_delta_pp=0, raw_runs_reconciled=2, same_complete_output_identity=True,
        scoring_and_full_contract_reused=True, deleted_csv_reread=False,
        archive_hash_reused_from_release=True, archive_size_rechecked=True,
        one_1b_candidate_run=True, baseline_cpu_historical=True,
        files=[identity(p) for p in (Path(__file__), ROOT/"1b-report.json",
               ROOT/"1b-freeze.json", old/"close-audit.json", old/"score-1b/accuracy.json",
               cpu_report)])
    write(ROOT/"independent-audit.json", result)
    print("EXP728_AUDIT", result["cpu_s"], result["accuracy"]["point_pp"], flush=True)


if __name__ == "__main__":
    main()
