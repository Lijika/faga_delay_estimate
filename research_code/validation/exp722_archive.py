#!/usr/bin/env python3
"""Relocate two verified historical archives before the full 1B run."""
from pathlib import Path
import shlex
import shutil
import subprocess
import time

from exp676_archive_output import remote
from exp709_cost_skeleton import read, check, identity, write

ROOT = Path("validation/results/exp722")
DESTINATION = Path("build/remote-output-archives/exp722")


def main():
    assert read(ROOT/"package-check.json")["all_passed"]
    assert not DESTINATION.exists()
    old580 = read("validation/results/exp598/old-billion-cleanup-complete.json")["deleted"]
    old598 = read("validation/results/exp602/exp598-output-archive-verified.json")
    assert old598["full_roundtrip_passed"]
    files = []
    for previous, source in ((old580, old580["archive"]),
                             (old598, old598["original"]["archive"])):
        prior = previous.get("original", previous)
        files.append(dict(source=source, destination=str(DESTINATION/source),
            expected=dict(path=source, bytes=previous["archive_bytes"], sha256=previous["archive_sha256"]),
            rebuild_command=prior["rebuild_command"],
            decompressed_sha256=previous["decompressed_sha256"],
            restore_command=["rsync", "-a", str(DESTINATION/source), "r9r4900:lhjwork/eda2026/"+source]))
    assert len(files) == len({f["source"] for f in files}) == 2
    assert shutil.disk_usage(".").free > sum(f["expected"]["bytes"] for f in files)+20_000_000_000
    for p in (ROOT/"rsync-local-help.txt", ROOT/"rsync-r9-help.txt"):
        assert "--files-from" in p.read_text() and "--archive" in p.read_text()
    write(ROOT/"archive-plan.json", dict(files=files, named_inputs=False,
        active_consumers_checked=["exp720 independent audit", "exp722 clean", "exp722 billion and score"],
        current_program_measurements_complete=True, local_free_start_bytes=shutil.disk_usage(".").free,
        remote_df_start=remote("df -B1 .")))
    listing = ROOT/"archive-files.txt"
    listing.write_text("".join(f["source"]+"\n" for f in files))
    DESTINATION.mkdir(parents=True)
    command = ["rsync", "-a", "--files-from="+str(listing),
               "r9r4900:lhjwork/eda2026/", str(DESTINATION)+"/"]
    start = time.monotonic()
    print("EXP722_ARCHIVE_TRANSFER", [f["source"] for f in files], flush=True)
    with (ROOT/"archive-transfer.stdout").open("x") as out, (ROOT/"archive-transfer.stderr").open("x") as err:
        subprocess.run(command, stdout=out, stderr=err, check=True, timeout=3600)
    verified = []
    for i, item in enumerate(files):
        actual = check(item["destination"], item["expected"])
        quoted = shlex.quote(item["source"])
        source_sha = remote("sha256sum -- "+quoted, timeout=300).split()[0]
        assert source_sha == actual["sha256"]
        metadata = remote("stat -c '%s %Y %i' -- "+quoted).strip()
        assert int(metadata.split()[0]) == actual["bytes"]
        record = dict(item, local=actual, source_metadata=metadata, full_hashes_match=True)
        write(ROOT/f"archive-verified-{i}.json", record)
        print("EXP722_REMOVE_VERIFIED_REMOTE_COPY", item["source"], actual["bytes"], source_sha, flush=True)
        remote("test \"$(stat -c '%s %Y %i' -- "+quoted+")\" = "+shlex.quote(metadata)+
               " && rm -- "+quoted+" && test ! -e "+quoted)
        write(ROOT/f"archive-deleted-{i}.json", dict(record, deleted=True))
        verified.append(record)
    write(ROOT/"archive-cleanup.json", dict(files=verified, full_hashes_match=True,
        released_remote_bytes=sum(f["expected"]["bytes"] for f in files),
        local_free_end_bytes=shutil.disk_usage(".").free, remote_df_end=remote("df -B1 ."),
        wall_s=time.monotonic()-start, command=command, script=identity(__file__)))
    print("EXP722_ARCHIVE_COMPLETE", flush=True)


if __name__ == "__main__":
    main()
