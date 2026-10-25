#!/usr/bin/env python3
"""Retain exact row-aligned delay archives after the 1B run and audit finish."""
from pathlib import Path
import shutil
import socket
import subprocess
import time

from exp722_column_archive import restored, read, write, identity, check

ROOT = Path("validation/results/exp722")
BUILD = Path("build/exp722/column-archives")


def main():
    assert socket.gethostname() == "lhj-R4900-G3"
    assert Path.cwd() == Path("/home/lhj/lhjwork/eda2026/research/exp722")
    assert read(ROOT/"close-audit.json")["all_checks_passed"]
    assert read(ROOT/"column-archive-self-check.json")["roundtrip_passed"]
    old = read("../exp720/validation/results/exp720/100m-report.json")
    current = read(ROOT/"1b-report.json")
    items = [
        dict(name="exp720-A-100m", root=Path("../exp720"), input=old["input"],
             output=old["evidence"]["A"]["output"], command=old["evidence"]["A"]["run"]["command"]),
        dict(name="exp722-1b", root=Path("."), input=current["input"],
             output=current["output"], command=current["run"]["command"]),
    ]
    write(ROOT/"retention-plan.json", dict(
        files=[dict(i, root=str(i["root"])) for i in items], driver=identity(__file__),
        preserve_next_100m_reference="../exp720/build/exp720/100m-0-C.csv",
        active_measurement=False, keep_named_inputs=True, disk_free_start_bytes=shutil.disk_usage(".").free))
    start = time.monotonic()
    records = []
    for item in items:
        source, request = item["root"]/item["output"]["path"], item["root"]/item["input"]["path"]
        archive = BUILD/(item["name"]+"-delay.csv.zst")
        assert not archive.exists() and shutil.disk_usage(".").free > 400_000_000
        before = source.stat()
        request_before = request.stat()
        assert request_before.st_size == item["input"]["bytes"]
        command = ["cut", "-d,", "-f3", str(source)]
        with archive.open("xb") as output, (ROOT/(item["name"]+"-retain.stderr")).open("xb") as err:
            cut = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=err)
            compressor = subprocess.Popen(["zstd", "--single-thread", "-1", "--check", "-q", "-c"],
                                          stdin=cut.stdout, stdout=output, stderr=err)
            cut.stdout.close()
            codes = [compressor.wait(), cut.wait()]
        assert codes == [0, 0], codes
        actual = restored(request, archive, ROOT/(item["name"]+"-restore.stderr"))
        assert all(actual[k] == item["output"][k] for k in ("bytes", "sha256"))
        check(source, item["output"])
        after = source.stat()
        request_after = request.stat()
        assert (before.st_size, before.st_mtime_ns, before.st_ino) == (
            after.st_size, after.st_mtime_ns, after.st_ino)
        assert (request_before.st_size, request_before.st_mtime_ns, request_before.st_ino) == (
            request_after.st_size, request_after.st_mtime_ns, request_after.st_ino)
        record = dict(source=str(source), original=item["output"], input=item["input"],
            archive=identity(archive), restored=actual, full_roundtrip_passed=True,
            source_metadata=[before.st_size, before.st_mtime_ns, before.st_ino],
            rebuild_cwd=str(item["root"]), rebuild_command=item["command"],
            restore_shell="bash", restore_command=f"paste -d, {request} <(zstd -dq -c {archive}) > {source}")
        write(ROOT/(item["name"]+"-retain-verified.json"), record)
        print("EXP722_REMOVE_RETAINED_OUTPUT", source, before.st_size, actual["sha256"], flush=True)
        source.unlink()
        record.update(deleted=True, net_released_bytes=before.st_size-archive.stat().st_size)
        write(ROOT/(item["name"]+"-retained.json"), record)
        records.append(record)
    write(ROOT/"retention-complete.json", dict(all_checks_passed=True, files=records,
        net_released_bytes=sum(v["net_released_bytes"] for v in records),
        disk_free_end_bytes=shutil.disk_usage(".").free, wall_s=time.monotonic()-start))
    print("EXP722_RETENTION_COMPLETE", shutil.disk_usage(".").free, flush=True)


if __name__ == "__main__":
    main()
