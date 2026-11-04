"""Capture the local audit corpus without running or changing the estimator."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import csv
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import zipfile

OUT = Path(__file__).resolve().parents[1]
ROOT = OUT.parents[1]
EAT = ROOT.parent / "EDA2026_EAT"
RELEASE = ROOT / "subm/versions/exp853-eat243-lossless-directory-20261104"


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True)


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def inventory(base, dest, exclude=()):
    """Record logical bytes; do not follow symlinks or hash large data."""
    stats = defaultdict(lambda: {"files": 0, "logical_bytes": 0, "symlinks": 0})
    errors = []
    with gzip.open(dest, "wt", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["path", "kind", "logical_bytes", "mtime_ns", "symlink_target"])
        for directory, dirs, files in os.walk(base, followlinks=False,
                                               onerror=lambda e: errors.append(str(e))):
            dirs[:] = sorted(d for d in dirs if Path(directory, d) not in exclude
                             and d != ".git")
            for name in sorted(files + [d for d in dirs if Path(directory, d).is_symlink()]):
                p = Path(directory, name)
                try:
                    st = p.lstat()
                    rel = p.relative_to(base)
                    link = p.is_symlink()
                    writer.writerow([str(rel), "symlink" if link else "file", st.st_size,
                                     st.st_mtime_ns, os.readlink(p) if link else ""])
                    item = stats[rel.parts[0]]
                    item["files"] += not link
                    item["symlinks"] += link
                    item["logical_bytes"] += 0 if link else st.st_size
                except OSError as exc:
                    errors.append(f"{p}: {exc}")
    return {"by_top_level": dict(stats), "files": sum(s["files"] for s in stats.values()),
            "logical_bytes": sum(s["logical_bytes"] for s in stats.values()), "errors": errors}


def main():
    assert (ROOT / "RESULTS.md").is_file() and RELEASE.is_dir()
    index = OUT / "index"
    evidence = OUT / "evidence"
    index.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    status = git("status", "--porcelain=v1", "-uall")
    (index / "git-status-before.txt").write_text(status)
    (index / "git-history-all.tsv").write_text(git(
        "log", "--all", "--date=iso-strict", "--format=%H%x09%aI%x09%cI%x09%s"))
    (index / "git-refs.tsv").write_text(git(
        "for-each-ref", "--format=%(refname)%09%(objectname)%09%(committerdate:iso-strict)"))
    rows, copied = [], []
    families = {
        "exact_or_search": r"exact|Dijkstra|A\*|真实路径|上界|下界|父链",
        "compressed_or_table": r"压缩|码本|查表|目录|曲面|residue",
        "learning": r"XGBoost|PySR|学习|训练|残差|模型",
        "performance": r"CPU|SIMD|预取|解析|吞吐",
        "resources": r"ELF|RSS|100MB|2GB|容量",
        "failure_or_limit": r"失败|未过|超限|停止|不通过|未通过",
        "release": r"正式接入|发布|交付|打包",
    }

    def copy(source, relative):
        dest = evidence / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        digest = sha(source)
        assert sha(dest) == digest
        copied.append({"source": str(source), "copy": str(dest.relative_to(OUT)),
                       "bytes": source.stat().st_size, "sha256": digest})

    for p in sorted((ROOT / "experiment").glob("*.md")):
        text = p.read_text(encoding="utf-8")
        match = re.match(r"实验(\d+)", p.name)
        dates = re.findall(r"2026-\d{2}-\d{2}", text)
        title = next((s.lstrip("# ").strip() for s in text.splitlines() if s.startswith("#")),
                     p.stem)
        rows.append({
            "number": int(match.group(1)) if match else "",
            "filename": p.name, "title": title, "bytes": p.stat().st_size,
            "sha256": sha(p), "first_date_in_text": dates[0] if dates else "",
            "mtime_ns": p.stat().st_mtime_ns,
            "tags_automatic_not_verdict": "|".join(k for k, v in families.items()
                                                  if re.search(v, text, re.I)),
        })
        copy(p, Path("experiment") / p.name)
    with (index / "experiments.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        w = csv.DictWriter(stream, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    assert len({r["filename"] for r in rows}) == len(rows)

    for name in ("RESULTS.md", "DESIGN.md", "AGENTS.md", "README.md"):
        p = ROOT / name
        if p.exists():
            copy(p, Path("project") / name)
    copy(Path("/tmp/eda2026-handoff-skydiscover-eat-20261104.md"),
         Path("project/handoff-20261104-1618-CST.md"))
    copy(ROOT / "doc/EDA2026赛题一-MinerU-flash.md", Path("rules/赛题V0.3解析.md"))
    for name in ("补充信息.md", "qa.md"):
        copy(Path("/mnt/d/obsidian_work/竞赛/EDA2026/赛题测试集") / name,
             Path("rules") / name)
    for p in sorted(RELEASE.glob("*.md")) + sorted(RELEASE.glob("*.json")):
        copy(p, Path("formal243") / p.name)
    for p in sorted((RELEASE / "evidence").glob("*")):
        if p.is_file():
            copy(p, Path("formal243/evidence") / p.name)
    for name in ("rebuild.py", "check_release_1m.py"):
        copy(RELEASE / name, Path("formal243") / name)
    for p in sorted((RELEASE / "source").rglob("*")):
        if p.is_file() and p.name != "libzstd.a":
            copy(p, Path("formal243") / p.relative_to(RELEASE))
    main181 = EAT / "results/pipeline/exp853-eat197-native181-requeue-packet/main-terminal"
    for p in sorted(main181.glob("*.json")):
        if p.name != "summary.json":
            copy(p, Path("eat181-terminal") / p.name)
    # The summary contains large repeated stat tables; retain its identity and a narrow extract.
    d = json.loads((main181 / "summary.json").read_text())
    write_json(evidence / "eat181-terminal/summary-extract.json", {
        "source": str(main181 / "summary.json"), "source_sha256": sha(main181 / "summary.json"),
        "fields": {k: d[k] for k in ("all_checks_passed", "qualified", "error",
                                    "official_five_run_certificate", "timing_scope")},
        "binary": d["context"]["binary"],
        "note": "Selected fields; original remains in source directory."})
    write_json(index / "copied-evidence.json", copied)

    inventories = {}
    for label, base, excludes in (
        ("workspace", ROOT, (OUT,)),
        ("validation-results", ROOT / "validation/results", ()),
        ("eat-results", EAT / "results", ()),
    ):
        inventories[label] = inventory(base, index / f"{label}.csv.gz", excludes)
    decisions = []
    for p in sorted((EAT / "results/pipeline").rglob("*.json")):
        if not any(s in p.name.lower() for s in ("review", "round_summary", "decision")):
            continue
        if p.stat().st_size > 300_000:
            continue
        try:
            d = json.loads(p.read_text())
            if isinstance(d, dict):
                fields = {k: v for k, v in d.items()
                          if isinstance(v, (str, int, float, bool, type(None)))
                          and re.search(r"status|decision|accepted|passed|qualified|complete|"
                                        r"promot|verdict|gain|reason|scope", k, re.I)}
                if fields:
                    decisions.append({"path": str(p.relative_to(EAT)), "bytes": p.stat().st_size,
                                      "mtime_ns": p.stat().st_mtime_ns, "fields": fields})
        except (OSError, UnicodeError, ValueError):
            continue
    with (index / "eat-decision-fields.jsonl").open("w") as stream:
        for row in decisions:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    with zipfile.ZipFile(index / "experiment-corpus.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted((evidence / "experiment").glob("*.md")):
            z.write(p, "experiment/" + p.name)
    with zipfile.ZipFile(index / "experiment-corpus.zip") as z:
        assert len(z.namelist()) == len(rows)
        assert z.testzip() is None
        for r in rows:
            assert hashlib.sha256(z.read("experiment/" + r["filename"])).hexdigest() == r["sha256"]
    write_json(index / "snapshot.json", {
        "started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(),
        "root": str(ROOT), "branch": git("branch", "--show-current").strip(),
        "head": git("rev-parse", "HEAD").strip(),
        "commits_head": int(git("rev-list", "--count", "HEAD")),
        "commits_all": int(git("rev-list", "--all", "--count")),
        "status_paths": len(status.splitlines()),
        "status_codes": dict(Counter(s[:2] for s in status.splitlines())),
        "experiments": len(rows), "experiment_bytes": sum(r["bytes"] for r in rows),
        "unique_experiment_numbers": len({r["number"] for r in rows if r["number"] != ""}),
        "experiment_number_min": min(r["number"] for r in rows if r["number"] != ""),
        "experiment_number_max": max(r["number"] for r in rows if r["number"] != ""),
        "automatic_tag_counts": dict(Counter(t for r in rows for t in
                                             r["tags_automatic_not_verdict"].split("|") if t)),
        "inventories": inventories, "decision_files_extracted": len(decisions),
        "root_estimate": {"bytes": (ROOT / "estimate").stat().st_size,
                          "sha256": sha(ROOT / "estimate")},
        "formal_estimate": {"bytes": (RELEASE / "bin-estimate").stat().st_size,
                            "sha256": sha(RELEASE / "bin-estimate")},
        "notes": ["No algorithm execution; no result-file contents globally verified.",
                  "Inventories are sequential snapshots, not a filesystem transaction.",
                  "Logical sizes count hard-linked files per path; .git excluded.",
                  "Prior worktree changes preserved; audit output excluded from workspace inventory."]})
    assert status == git("status", "--porcelain=v1", "-uall"), "worktree status changed during capture"
    print(json.dumps({"experiments": len(rows), "decision_files": len(decisions),
                      "output": str(OUT), "copied_bytes": sum(x["bytes"] for x in copied)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
