#!/usr/bin/env python3
"""Separate real-map error from exact nominal-table representation error."""
import csv
import json
from pathlib import Path
import time

import numpy as np

from exp413_affine_tail import Field, accumulate, identity

ROOT = Path("validation/results/exp416")
GOLDEN = Path("doc/eda比赛文件/data/delay_estimate_ans.csv")


def split(pin):
    cell, port = pin.split("/")
    prefix, x, y = cell.split("_")
    assert prefix == "SRB"
    return int(x), int(y), port


def run():
    started = time.process_time()
    fields = {"ZSEA[0]": Field("build/exp413/sea.bin"),
              "ZLE[0]": Field("build/exp413/le.bin")}
    ports = [p["Name"] for p in json.loads(
        Path("doc/eda比赛文件/arch/SRB_Port.json").read_text())["Port"]]
    ordinal = {ports[int(p)]: i for i, p in enumerate(fields["ZSEA[0]"].ports)}
    gap = json.loads(Path("doc/eda比赛文件/arch/SRB_Gap.json").read_text())["Gap"]
    prefix = {direction: np.array([sum(line["delay"] for line in gap["Line"]
                                      if line["direction"] == direction and line["site"] < x)
                                  for x in range(size)], dtype=int)
              for direction, size in (("vertical", 120), ("horizontal", 550))}
    assert prefix["vertical"][0] == prefix["horizontal"][0] == 0
    rows, scanned = [], 0
    with GOLDEN.open(newline="") as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == ["From", "To", "delay"]
        for row in reader:
            assert None not in row and all(v is not None for v in row.values())
            scanned += 1
            sp = row["From"].split("/")[-1]
            if sp not in fields:
                continue
            sx, sy, sp = split(row["From"])
            tx, ty, tp = split(row["To"])
            if tp not in ordinal:
                continue
            truth = int(row["delay"])
            assert truth >= 0
            nominal = int(fields[sp].row([tx-sx], ty-sy)[0, ordinal[tp]])
            line = int(abs(prefix["vertical"][tx] - prefix["vertical"][sx]) +
                       abs(prefix["horizontal"][ty] - prefix["horizontal"][sy]))
            near_boundary = min(sx, 119-sx, tx, 119-tx, sy, 549-sy, ty, 549-ty) <= 12
            intersects = any(max(min(sx, tx), b["left"]) <= min(max(sx, tx), b["right"])
                             and max(min(sy, ty), b["lower"]) <= min(max(sy, ty), b["upper"])
                             for b in gap["Block"])
            rows.append({"from": row["From"], "to": row["To"], "source": sp,
                         "exact": truth, "nominal": nominal, "line": line,
                         "predicted": nominal+line, "boundary": near_boundary,
                         "block_rectangle": intersects,
                         "regular_proxy": not near_boundary and not intersects,
                         "near_axis": min(abs(tx-sx), abs(ty-sy)) < 12})
    assert scanned == 1000000 and rows
    stats, truth = {}, np.array([r["exact"] for r in rows])
    prediction = np.array([r["predicted"] for r in rows])
    masks = {"all": np.ones(len(rows), dtype=bool)}
    for field in ("boundary", "block_rectangle", "regular_proxy", "near_axis"):
        masks[field] = np.array([r[field] for r in rows], dtype=bool)
    for source in fields:
        masks[source] = np.array([r["source"] == source for r in rows])
        masks[source+"/regular_proxy"] = masks[source] & masks["regular_proxy"]
    for mode, predicted in (("raw", prediction), ("bias_minus3", np.maximum(0, prediction-3))):
        for name, mask in masks.items():
            accumulate(stats, mode+"/"+name, truth, predicted, mask)
    for entry in stats.values():
        entry["accuracy_pp"] = 100*entry["score_sum"]/entry["rows"]
        entry["mean_absolute_error"] = entry["error_sum"]/entry["rows"]
        entry["mean_relative_error"] = entry["relative_sum"]/entry["rows"]
    worst = sorted(rows, key=lambda r: abs(r["predicted"]-r["exact"]) / max(1, r["exact"]),
                   reverse=True)[:20]
    with (ROOT/"rows.csv").open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    report = {"golden": identity(GOLDEN), "full_golden_rows_scanned": scanned,
              "selected_rows": len(rows), "stats": stats, "worst": worst,
              "raw_gate_pass": stats["raw/all"]["accuracy_pp"] >= 98 and all(
                  stats["raw/"+s+"/regular_proxy"]["accuracy_pp"] >= 99 for s in fields),
              "cpu_s": time.process_time()-started,
              "scope": "Public development subset for two source Z ports and Z targets only; "
                       "not full request accuracy or an end-to-end runtime measurement."}
    (ROOT/"report.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k not in ("stats","worst")},indent=2))


if __name__ == "__main__":
    run()
