#!/usr/bin/env python3
"""Keep historical CSV outputs as exact input plus compressed delay column."""
import hashlib
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path("../exp709/validation").resolve()))
from exp709_cost_skeleton import check, identity, read, write

ROOT = Path("validation/results/exp722")
BUILD = Path("build/exp722/column-archives")


def encode(source, target, errors):
    with target.open("xb") as output, errors.open("xb") as err:
        decode = subprocess.Popen(["zstd", "-dq", "-c", str(source)], stdout=subprocess.PIPE, stderr=err)
        cut = subprocess.Popen(["cut", "-d,", "-f3"], stdin=decode.stdout, stdout=subprocess.PIPE, stderr=err)
        decode.stdout.close()
        compress = subprocess.Popen(["zstd", "--single-thread", "-1", "--check", "-q", "-c"],
                                    stdin=cut.stdout, stdout=output, stderr=err)
        cut.stdout.close()
        codes = [compress.wait(), cut.wait(), decode.wait()]
    assert codes == [0, 0, 0], codes


def restored(request, archive, errors):
    digest, size = hashlib.sha256(), 0
    with errors.open("xb") as err:
        decode = subprocess.Popen(["zstd", "-dq", "-c", str(archive)], stdout=subprocess.PIPE, stderr=err)
        fd = decode.stdout.fileno()
        paste = subprocess.Popen(["paste", "-d,", str(request), f"/proc/self/fd/{fd}"],
                                 pass_fds=(fd,), stdout=subprocess.PIPE, stderr=err)
        decode.stdout.close()
        for block in iter(lambda: paste.stdout.read(8 << 20), b""):
            digest.update(block)
            size += len(block)
        paste.stdout.close()
        codes = [paste.wait(), decode.wait()]
    assert codes == [0, 0], codes
    return dict(bytes=size, sha256=digest.hexdigest())


def self_check():
    with tempfile.TemporaryDirectory(dir=BUILD) as folder:
        folder = Path(folder)
        request = b"From,To\nX0Y0/A,X1Y1/B\nX9Y9/C,X8Y8/D\nX7Y7/A,X7Y7/A\n"
        original = b"From,To,delay\nX0Y0/A,X1Y1/B,1234\nX9Y9/C,X8Y8/D,-1\nX7Y7/A,X7Y7/A,0\n"
        (folder/"request.csv").write_bytes(request)
        encoded = subprocess.run(["zstd", "--single-thread", "-q", "-c"], input=original,
                                 capture_output=True, check=True).stdout
        (folder/"original.zst").write_bytes(encoded)
        encode(folder/"original.zst", folder/"delays.zst", folder/"encode.stderr")
        actual = restored(folder/"request.csv", folder/"delays.zst", folder/"restore.stderr")
        assert actual == dict(bytes=len(original), sha256=hashlib.sha256(original).hexdigest())
    write(ROOT/"column-archive-self-check.json", dict(roundtrip_passed=True, rows=3,
                                                    header=True, zero=True, negative=True))


def main():
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp722")
    assert not BUILD.exists()
    BUILD.mkdir(parents=True)
    help_text = (ROOT/"column-archive-command-help.txt").read_text()
    assert "--fields" in help_text and "--delimiters" in help_text and "--single-thread" in help_text
    self_check()
    plan = read(ROOT/"archive-plan.json")
    expected_input = read("../exp708/validation/results/exp708/1b-report.json")["input"]
    for experiment in (580, 598):
        assert read(f"../exp{experiment}/validation/results/exp{experiment}/1b-report.json")["input"] == expected_input
    request = Path(expected_input["path"])
    check(request, expected_input)
    started = time.monotonic()
    input_stat = request.stat()
    results = []
    write(ROOT/"column-archive-plan.json", dict(
        files=plan["files"], input=expected_input, driver=identity(__file__),
        selected_columns="cut -d, -f3; includes delay header",
        current_consumers=plan["active_consumers_checked"],
        disk_free_start_bytes=shutil.disk_usage(".").free,
        timing_running=False, keep_input=True, verify_full_reconstructed_output_before_delete=True))
    for experiment, item in zip((580, 598), plan["files"]):
        source = Path("../..")/item["source"]
        expected = item["expected"]
        before = source.stat()
        check(source, expected)
        archive = BUILD/f"exp{experiment}-1b-delay.csv.zst"
        print("EXP722_COLUMN_ARCHIVE_START", experiment, flush=True)
        encode(source, archive, ROOT/f"column-encode-{experiment}.stderr")
        restored_output = restored(request, archive, ROOT/f"column-restore-{experiment}.stderr")
        assert restored_output["sha256"] == item["decompressed_sha256"]
        old = read(f"../exp{experiment}/validation/results/exp{experiment}/1b-report.json")
        assert old["rows"] == 1_000_000_000
        current_input = request.stat()
        assert (input_stat.st_size, input_stat.st_mtime_ns, input_stat.st_ino) == (
            current_input.st_size, current_input.st_mtime_ns, current_input.st_ino)
        after = source.stat()
        assert (before.st_size, before.st_mtime_ns, before.st_ino) == (
            after.st_size, after.st_mtime_ns, after.st_ino)
        record = dict(original_archive=expected, input=expected_input, archive=identity(archive),
            restored_output=restored_output, complete_output_sha_matches=True, rows=1_000_000_000,
            rebuild_command=item["rebuild_command"],
            restore_command=f"paste -d, {request} <(zstd -dq -c {archive})",
            restore_shell="bash", original_stat=[before.st_size, before.st_mtime_ns, before.st_ino])
        write(ROOT/f"column-verified-{experiment}.json", record)
        print("EXP722_REMOVE_REENCODED_ARCHIVE", source, before.st_size, expected["sha256"], flush=True)
        source.unlink()
        record.update(deleted=True, net_released_bytes=before.st_size-archive.stat().st_size)
        write(ROOT/f"column-deleted-{experiment}.json", record)
        results.append(record)
    write(ROOT/"column-archive-complete.json", dict(files=results, all_checks_passed=True,
        net_released_bytes=sum(r["net_released_bytes"] for r in results),
        disk_free_end_bytes=shutil.disk_usage(".").free, wall_s=time.monotonic()-started))
    print("EXP722_COLUMN_ARCHIVE_COMPLETE", shutil.disk_usage(".").free, flush=True)


if __name__ == "__main__":
    main()
