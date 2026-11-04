#!/usr/bin/env python3
"""Check the measured release ELF on every row of the accepted exposed 1M."""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import time
import signal
import sys

WORK = Path(__file__).resolve().parent
INPUT = Path("/home/lhjysyx/EDA2026_EAT/candidate/work_eat176_native_representation_check/full1m-requests.csv")
ELF_SHA = "69df6c6c0f8cb119e742b2662c609997be9f381681090dca1751ed4a97868c02"
INPUT_SHA = "4a07a210efa8db99882ea0d5d2aae1bf75a4c5c7ec8b2b0e9751fbeb297efb57"
OUTPUT_SHA = "816dae0f769274cf2f940af92c9f538586d05599a88aa3dd3b9ee10581ec22c9"
PRED_SHA = "8e0fbaa5b890ec7b130f48c09eb988456919e8969d81ec727958d3e192eb98e0"


def identity(path):
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def main():
    if sys.flags.optimize:
        raise RuntimeError("run without -O; full1M verification uses assertions")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--input", type=Path, default=INPUT)
    args = parser.parse_args()
    artifact = args.out.resolve()
    artifact.mkdir(parents=True, exist_ok=False)
    input_path = args.input.resolve()
    prereg = {
        "at": datetime.datetime.now().astimezone().isoformat(),
        "hypothesis": "The actual r9 release ELF preserves accepted complete1M predictions and output/resource gates.",
        "replaced_mandatory_work": "Deployment check of accepted lossless full-domain directory representation.",
        "accuracy_mechanism": "Reuse exact accepted243 source and five asset payloads.",
        "resource_budget": {"prediction_memfd_bytes": 40_136_160, "estimator_rss_limit_bytes": 2_000_000_000, "wall_limit_s": 3600},
        "data_split": "All1,000,000 historically exposed development requests; exact output parity to accepted checker.",
        "expected_gain": "No expected prediction change from accepted local1M; r9 CPU benefit reuses Main's accepted1B.",
        "stopping_condition": "Any changed CSV byte, invalid row, static/size/resource failure rejects release.",
        "no_independent_1b": True,
    }
    (artifact / "full1m-preregistration.json").write_text(json.dumps(prereg, indent=2) + "\n")
    with Path("/home/lhjysyx/EDA2026_EAT/candidate/work_eat038-local-heavy.lock").open("r") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        elf = args.elf.resolve()
        binary = identity(elf)
        assert binary["sha256"] == ELF_SHA and binary["bytes"] == 86_937_624
        inp = identity(input_path)
        assert inp["sha256"] == INPUT_SHA and inp["bytes"] == 35_198_280
        ph = subprocess.check_output(["readelf", "-lW", str(elf)], text=True)
        dyn = subprocess.check_output(["readelf", "-dW", str(elf)], text=True)
        (artifact / "release-elf-program-headers.txt").write_text(ph)
        (artifact / "release-elf-dynamic-section.txt").write_text(dyn)
        assert "INTERP" not in ph and "(NEEDED)" not in dyn
        clean = artifact / "cleanroom"
        clean.mkdir()
        target = clean / "estimate"
        assert not target.exists()
        os.link(elf, target)
        descriptor = os.memfd_create("eat248-release-full1m", os.MFD_CLOEXEC)
        output = Path(f"/proc/{os.getpid()}/fd/{descriptor}")
        log = artifact / "release-full1m.time.log"
        err = artifact / "release-full1m.stderr.log"
        command = ["/usr/bin/time", "-v", "-o", str(log), str(target),
                   "-in", str(input_path), "-out", str(output)]
        maximum_threads = 0
        started = time.monotonic()
        with err.open("w") as stderr:
            process = subprocess.Popen(command, cwd=clean, env={}, stdout=subprocess.DEVNULL,
                                       stderr=stderr, start_new_session=True)
            try:
                while process.poll() is None:
                    if time.monotonic() - started > 3600:
                        raise TimeoutError("complete1M release check exceeded3600s")
                    try:
                        children = Path(f"/proc/{process.pid}/task/{process.pid}/children").read_text().split()
                        for pid in children:
                            status = Path(f"/proc/{pid}/status").read_text()
                            match = re.search(r"^Threads:\s+(\d+)", status, re.M)
                            if match:
                                maximum_threads = max(maximum_threads, int(match[1]))
                    except FileNotFoundError:
                        pass
                    time.sleep(.002)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                returncode = process.wait()
        wall = time.monotonic() - started
        assert returncode == 0, err.read_text()
        text = log.read_text()
        def measured(pattern):
            match = re.search(pattern, text)
            assert match, pattern
            return float(match[1])
        user = measured(r"User time \(seconds\): ([0-9.]+)")
        system = measured(r"System time \(seconds\): ([0-9.]+)")
        rss = int(measured(r"Maximum resident set size \(kbytes\): (\d+)")) * 1024
        assert maximum_threads == 1 and rss <= 2_000_000_000
        prediction_sha = hashlib.sha256()
        with input_path.open("rb") as request, output.open("rb") as result:
            assert request.readline() == b"From,To\n"
            assert result.readline() == b"From,To,delay\n"
            for row in range(1_000_000):
                expected = request.readline()
                actual = result.readline()
                assert expected.endswith(b"\n") and actual.endswith(b"\n"), row
                endpoints, comma, value = actual[:-1].rpartition(b",")
                assert comma and endpoints == expected[:-1] and endpoints.count(b",") == 1, row
                delay = int(value)
                assert delay >= 0 and str(delay).encode() == value, row
                prediction_sha.update(struct.pack("<i", delay))
            assert request.read(1) == b"" and result.read(1) == b""
        result_id = identity(output)
        assert result_id["sha256"] == OUTPUT_SHA and result_id["bytes"] == 40_136_160
        assert prediction_sha.hexdigest() == PRED_SHA
        assert identity(elf) == binary and identity(input_path) == inp
        os.close(descriptor)
        report = {
            "schema": "eat248-actual-release-elf-full1m-v1",
            "at": datetime.datetime.now().astimezone().isoformat(),
            "passed": True, "rows": 1_000_000, "binary": binary, "input": inp,
            "output": result_id, "prediction_i32_sha256": prediction_sha.hexdigest(),
            "run": {"command": command, "cwd": str(clean), "environment": {},
                    "user_cpu_s": user, "sys_cpu_s": system, "cpu_s": user + system,
                    "wall_s": wall, "exit_code": returncode,
                    "threads_observed": maximum_threads, "peak_rss_bytes": rss},
            "contract": {"header": True, "all_endpoints": True, "row_order": True,
                         "row_count": True, "three_fields": True, "canonical_integer": True,
                         "final_newline": True, "exact_eof": True},
            "static_elf_lt100MB": True,
            "output_storage": "anonymous memfd closed after full contract and SHA",
            "cleanroom": {"directory_files": sorted(p.name for p in clean.iterdir()),
                          "assets_in_cwd": False, "empty_environment": True,
                          "filesystem_namespace_isolation": False},
            "accuracy": {"reused_from": "/home/lhjysyx/EDA2026_EAT/results/iteration-176/artifacts/native_representation_checker/checks-1m.json",
                         "complete_output_sha_equal": True, "weighted_acc_percent": 98.8752701109582,
                         "scope": "Previously exposed full1M; no new accuracy sampling or tuning."},
            "consistency": {"reused_remote_same_elf_full1b_runs": 7,
                            "official_consecutive_five_verified": False},
            "scope": "Local AMD/WSL release gate; CPU includes initialize/parse/predict/write and is not a r9 timing claim.",
        }
        (artifact / "release-full1m-checks.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({k: report[k] for k in ["passed", "rows", "binary", "output", "run"]}, indent=2))


if __name__ == "__main__":
    main()
