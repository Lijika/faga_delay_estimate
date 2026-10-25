#!/usr/bin/env python3
"""Reuse the audited 100M generator, exact sampler and paired scoring protocol."""
import inspect
from pathlib import Path
import shutil
import socket
import subprocess
import sys

import numpy as np

import exp720_leaf_cli as cli
sys.path.insert(0, str(Path("../exp685/validation").resolve()))
import exp685_event_data as data
sys.path.insert(0, str(Path("../exp683/validation").resolve()))
import exp683_expanded_score as scoring

ROOT, BUILD, PLAN = cli.ROOT, cli.BUILD, cli.PLAN
read, write, identity, check = cli.read, cli.write, cli.identity, cli.check
ARMS, ROWS, SEED = ("A", "C"), 100_000_000, 20261027720


def configure(expanded=False):
    data.ROOT, data.BUILD, data.PLAN = ROOT, BUILD, PLAN
    data.ARMS, data.ROWS, data.COUNT, data.SEED = ARMS, ROWS, 32, SEED
    data.BINARIES = dict(A=cli.BASE/"estimate", C=BUILD/"estimate")
    data.configure(expanded=expanded)


def prepare():
    configure()
    scoring.self_check()
    adapted_score()
    assert all(decision_gates(-.02, -.04, -.09, True, .6, .1, True).values())
    assert not all(decision_gates(-.03001, -.04, -.09, True, .6, .1, True).values())
    assert not all(decision_gates(-.02, -.04, -.09, True, .4999, .1, True).values())
    assert not all(decision_gates(-.02, -.04, -.09, False, .6, .1, True).values())
    assert not (ROOT/"freeze.json").exists()
    assert read(ROOT/"numeric-audit.json")["all_checks_passed"]
    build = read(ROOT/"build-freeze.json")
    for item in build["files"]+list(build["binaries"].values()):
        check(item["path"], item)
    old = read("../exp685/validation/results/exp685/freeze.json")
    history = [Path("../exp685")/r["path"] for r in old["history"]]
    history.append(Path("../exp685/build/exp685/expanded/sample-requests.csv"))
    assert len(history) == len(set(p.resolve() for p in history))
    for item in old["expected_tools"]:
        check(Path("../..")/item["path"], item)
    for tool in (data.prior.HIDDEN/"make_hidden_suite", data.prior.HIDDEN/"check_hidden_suite",
                 Path("../../build/exp203/exact_labels"), data.prior.CHECKER):
        result = subprocess.run([str(tool), "--help"], capture_output=True, text=True)
        text = result.stdout+result.stderr
        assert "usage" in text.lower()
        (ROOT/(tool.name+"-help.txt")).write_text(text)
    sampler = Path("validation/exp683_stratified_sample.cpp")
    assert sampler.read_bytes() == Path("../exp683/validation/exp683_stratified_sample.cpp").read_bytes()
    population, sample = data.adaptation()
    (BUILD/"population.py").write_text(population)
    (BUILD/"sample.py").write_text(sample)
    files = [Path(__file__), Path(cli.__file__), Path(data.__file__), Path(data.sample.__file__),
             Path(data.prior.__file__), Path(data.fresh.__file__), Path(data.labels.__file__),
             PLAN, ROOT/"protocol-original.md", ROOT/"build-freeze.json", ROOT/"numeric-audit.json",
             BUILD/"population.py", BUILD/"sample.py", sampler,
             data.prior.HIDDEN/"reach.bin", data.prior.HIDDEN/"independent/eligibility.bin",
             *data.ARCH.glob("*.json")]
    assert shutil.disk_usage(".").free > 28_000_000_000
    write(ROOT/"freeze.json", dict(files=[identity(p) for p in files],
        binaries=build["binaries"], checker=identity(data.prior.CHECKER), rows=ROWS,
        sample_rows=32*59904, samples_per_pair=32, proposal_rows=120_000_000,
        proposal_seed=20261025720, shuffle_seed=20261026720, seed=SEED,
        expected_tools=old["expected_tools"], history=[identity(p) for p in history],
        source_ports=data.labels.roles()[0], target_ports=data.labels.roles()[1],
        required_port_pairs=59904, schedule=[list(s) for s in ("AC", "AC", "CA", "AC", "CA", "AC", "CA")],
        sample_rule="32 without-replacement positions per port pair",
        cpu_label_budget_s=10_000, untouched_scores=True,
        complete_estimator_runs=0, disk_free_start_bytes=shutil.disk_usage(".").free))
    print("EXP720_NEW_100M_FROZEN", flush=True)


def dataset():
    configure()
    data.dataset()


def labels():
    configure()
    data.compute_labels()


def timing():
    configure()
    frozen = data.freeze_check()
    oracle = read(ROOT/"expanded/report.json")
    assert oracle["all_complete_label_checks"] and oracle["rows"] == 32*59904
    assert oracle["span_checks"] == 12
    assert all(r["exit_code"] == 0 and r["rss_bytes"] <= 2_000_000_000 for r in oracle["runs"])
    assert sum(r["cpu_s"] for r in oracle["runs"]) <= 10_000
    check(oracle["exact"]["path"], oracle["exact"])
    population = read(ROOT/"100m-input.json")
    request = Path(population["input"]["path"])
    check(request, population["input"])
    write(ROOT/"timing-freeze.json", dict(input=population["input"], labels=oracle["exact"],
        binaries=frozen["binaries"], schedule=frozen["schedule"],
        files=[identity(p) for p in (Path(__file__), ROOT/"freeze.json", ROOT/"expanded/report.json")],
        process_snapshot=subprocess.check_output(["ps", "-eo", "pid,etimes,pcpu,stat,args", "--sort=-pcpu"],
                                                 text=True),
        cpu=8, minimum_saved_100m_s=.5, minimum_score=.005, minimum_delta_pp=-.03,
        minimum_accuracy_lower_pp=-.05, minimum_group_delta_pp=-.10,
        confidence_per_component=.975, seed=SEED))
    times, evidence, runs, removed = {a: [] for a in ARMS}, {}, [], []
    for iteration, order in enumerate(frozen["schedule"]):
        for arm in order:
            output = BUILD/f"100m-{iteration}-{arm}.csv"
            assert not output.exists() and shutil.disk_usage(".").free > 5_100_000_000
            command = ["taskset", "-c", "8", str(data.BINARIES[arm]), "-in", str(request), "-out", str(output)]
            run = data.speed.measured(command, output.stem)
            assert run["threads"] == 1 and run["rss_bytes"] <= 2_000_000_000
            assert run["cpu_s"] < 100 and run["wall_s"] <= 3600
            counters = read(run["stderr"])
            assert counters == dict(rows=ROWS, unreachable=0, query_allocations=0)
            actual = identity(output)
            run.update(arm=arm, iteration=iteration, input=population["input"], output=actual, counters=counters)
            write(ROOT/(output.stem+"-evidence.json"), run)
            if iteration == 0:
                sampled = BUILD/f"{arm}-sample.csv"
                crun = data.speed.measured([str(data.prior.CHECKER), "check", str(request),
                    str(output), str(ROWS), str(BUILD/"expanded/positions.txt"), str(sampled)], arm+"-contract")
                contract = read(ROOT/(arm+"-contract.stdout"))
                assert contract["contract_passed"] and contract["rows"] == ROWS
                assert contract["sample_rows"] == 32*59904
                evidence[arm] = dict(output=actual, run=run, contract=contract, contract_run=crun,
                                     sample=identity(sampled))
            else:
                assert all(actual[k] == evidence[arm]["output"][k] for k in ("bytes", "sha256"))
                times[arm].append(run["cpu_s"])
                deletion = dict(file=actual, identical_to=evidence[arm]["output"], rebuild_command=command)
                write(ROOT/(output.stem+"-cleanup.json"), deletion)
                print("EXP720_REMOVE_DUPLICATE", output, actual["sha256"], flush=True)
                output.unlink()
                removed.append(deletion)
            runs.append(run)
            print("EXP720_TIMING", iteration, arm, run["cpu_s"], flush=True)
    write(ROOT/"100m-report.json", dict(rows=ROWS, unique_rows=ROWS, port_pairs=59904,
        input=population["input"], timing=times, evidence=evidence, runs=runs,
        deleted_duplicates=removed, released_bytes=sum(d["file"]["bytes"] for d in removed),
        accuracy_not_read=True, same_complete_run_cpu_and_accuracy=True,
        disk_free_end_bytes=shutil.disk_usage(".").free))


def adapted_score():
    text = inspect.getsource(scoring.main)
    changes = [
        ("base = Path('validation/results/exp683')/case", f"base = Path('{ROOT/'expanded'}')"),
        ("build = Path('build/exp683')/case", f"build = Path('{BUILD/'expanded'}')"),
        ("root = base/('score-'+report_path.parent.name)", f"root = Path('{ROOT/'score'}')"),
        ("    write(root/'accuracy.json',result)",
         "    result['V_predictions_unchanged'] = bool(np.array_equal(\n"
         "        predictions['A'][groups['event']==2], predictions['C'][groups['event']==2]))\n"
         "    write(root/'accuracy.json',result)"),
    ]
    for before, after in changes:
        assert text.count(before) == 1
        text = text.replace(before, after)
    compile(text, "exp720-score.py", "exec")
    return text


def decision_gates(point, lower, minimum, v_equal, saved, cpu_lower, combined):
    return dict(quality=point >= -.03 and lower >= -.05 and minimum >= -.10,
                V_unchanged=v_equal, cpu=saved >= .5 and cpu_lower > 0, combined=combined)


def score():
    configure()
    data.freeze_check()
    frozen = read(ROOT/"timing-freeze.json")
    for item in frozen["files"]:
        check(item["path"], item)
    source = BUILD/"score.py"
    source.write_text(adapted_score())
    report = read(ROOT/"100m-report.json")
    cached = {a: dict(source_output=e["output"], source_run=e["run"],
                     sample=e["sample"], contract=e["contract"], contract_run=e["contract_run"])
              for a, e in report["evidence"].items()}
    configure(expanded=True)
    namespace = dict(vars(scoring))
    exec(compile(source.read_text(), str(source), "exec"), namespace)
    namespace["main"]("100m", ROOT/"100m-report.json", cached)
    result = read(ROOT/"score/accuracy.json")
    delta = result["delta_accuracy"]
    minimum = min(v for key, group in result["group_delta_accuracy_pp"].items()
                  if key in ("distance", "near_axis", "direction") for v in group.values())
    joint = result["joint"]
    gates = decision_gates(delta["point_pp"], delta["conservative_ci975_pp"][0], minimum,
        result["V_predictions_unchanged"], joint["saved_cpu_s"], joint["ci975_saved_cpu_s"][0],
        joint["score_gate"])
    write(ROOT/"decision.json", dict(all_checks_passed=True, gates=gates, selected=all(gates.values()),
        minimum_primary_group_delta_pp=minimum, delta_accuracy=delta, joint=joint,
        accuracy=identity(ROOT/"score/accuracy.json"), report=identity(ROOT/"100m-report.json"),
        final_accuracy_above_99_verified=False, target_6242R_verified=False))
    print("EXP720_DECISION", gates, delta["point_pp"], joint, flush=True)


if __name__ == "__main__":
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp720")
    assert sys.argv[1:] in ([s] for s in ("prepare", "dataset", "labels", "timing", "score"))
    dict(prepare=prepare, dataset=dataset, labels=labels, timing=timing, score=score)[sys.argv[1]]()
