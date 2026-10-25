#!/usr/bin/env python3
"""Score in exp683's original directory so its frozen relative paths stay valid."""
import inspect
import os
from pathlib import Path
import socket
import sys
import time

sys.path.insert(0, str(Path("../exp683/validation").resolve()))
import exp683_expanded_score as scoring

read, write, identity = scoring.read, scoring.write, scoring.identity


def main():
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp722")
    origin = Path.cwd()
    root = Path("validation/results/exp722").resolve()
    report_path = root/"1b-report.json"
    report = read(report_path)
    assert report["all_checks_passed"] and report["rows"] == report["unique_rows"] == 1_000_000_000
    source = inspect.getsource(scoring.main)
    before = "root = base/('score-'+report_path.parent.name)"
    assert source.count(before) == 1
    source = source.replace(before, f"root = Path({str(root/'score-1b')!r})")
    start = source.index("    complete_reports = [report_path]")
    end = source.index("    assert report['port_pairs'] == 59904", start)
    source = source[:start]+"""    complete_reports = [report_path,
        Path('../exp708/validation/results/exp708/1b-report.json'),
        Path('../exp688/validation/results/exp688/1b-accuracy.json')]
    runs = {a: dict(output=e['output'], run=e['run'], input=report['input'])
            for a,e in report['evidence'].items()}
""" + source[end:]
    before = "    write(root/'accuracy.json',result)"
    assert source.count(before) == 1
    source = source.replace(before,
        "    result['V_predictions_unchanged'] = bool(np.array_equal(\n"
        "        predictions['A'][groups['event']==2], predictions['C'][groups['event']==2]))\n"+before)
    generated = Path("build/exp722/score-from-original-directory.py")
    generated.write_text(source)
    cached = {a: dict(source_output=e["output"], source_run=e["run"],
        sample=dict(e["sample"], path=str(Path(e["sample"]["path"]).resolve())),
        contract=e["contract"], contract_run=e["contract_run"]) for a,e in report["evidence"].items()}
    write(root/"score-reuse-freeze.json", dict(driver=identity(__file__), scorer=identity(scoring.__file__),
        generated=identity(generated), report=identity(report_path), cached_evidence=cached,
        original_score_cwd=str(origin.parent/"exp683"),
        reason="Original exp683 manifests contain paths relative to exp683; preserve that base.",
        complete_estimator_runs=0, new_exact_rows=0))
    namespace = dict(vars(scoring))
    exec(compile(source, str(generated.resolve()), "exec"), namespace)
    start, cpu = time.monotonic(), time.process_time()
    try:
        os.chdir("../exp683")
        namespace["main"]("1b", report_path, cached)
    finally:
        os.chdir(origin)
    result = read(root/"score-1b/accuracy.json")
    assert abs(result["accuracy"]["A"]["point_pp"]-98.65806165706272) < 1e-9
    delta = result["delta_accuracy"]
    minimum = min(v for k,g in result["group_delta_accuracy_pp"].items()
                  if k in ("distance", "direction", "near_axis") for v in g.values())
    gate = delta["point_pp"] >= -.03 and delta["conservative_ci975_pp"][0] >= -.05 and minimum >= -.10
    assert result["V_predictions_unchanged"]
    write(root/"1b-decision.json", dict(all_checks_passed=True, quality_gate=gate,
        minimum_group_delta_pp=minimum, delta=delta, accuracy=result["accuracy"]["C"],
        score=identity(root/"score-1b/accuracy.json"), report=identity(report_path),
        final_accuracy_above_99_verified=False, platform_verified=False,
        scoring_cpu_s=time.process_time()-cpu, scoring_wall_s=time.monotonic()-start))
    print("EXP722_1B_QUALITY", gate, result["accuracy"]["C"], delta, flush=True)


if __name__ == "__main__":
    main()
