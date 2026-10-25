#!/usr/bin/env python3
"""Freeze generated CSV identities and derive readable full-input coverage."""
import argparse
import collections
import hashlib
import json
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def summarize(stats, ports, tiles, nets, gaps, public):
    result = {}
    for side in ("from", "to"):
        port_counts, tile_counts = stats[f"{side}_port"], stats[f"{side}_tile"]
        z_groups = {key: collections.Counter() for key in ("direction", "span", "group", "lane")}
        for port, count in zip(ports, port_counts):
            name = port["Name"]
            if not name.startswith("Z"):
                continue
            head, lane = name.split("[")
            group = head[1]
            direction = head[2]
            if group == "S":
                group += head[3:]
            net = nets[name]
            z_groups["direction"][direction] += count
            z_groups["span"][str(abs(net["delta x"]) + abs(net["delta y"]))] += count
            z_groups["group"][group] += count
            z_groups["lane"][lane[:-1]] += count
        spatial = collections.Counter()
        edges = collections.Counter()
        corners = collections.Counter()
        line_near = collections.Counter()
        block_near = collections.Counter()
        for (x, y), count in zip(tiles, tile_counts):
            spatial[f"{x // 10},{y // 25}"] += count
            for name, yes in (("left", x <= 8), ("right", x >= 111),
                              ("bottom", y <= 8), ("top", y >= 541)):
                if yes:
                    edges[name] += count
            for name, yes in (("left-bottom", x <= 8 and y <= 8),
                              ("right-bottom", x >= 111 and y <= 8),
                              ("left-top", x <= 8 and y >= 541),
                              ("right-top", x >= 111 and y >= 541)):
                if yes:
                    corners[name] += count
            for line in gaps["Line"]:
                coordinate = x if line["direction"] == "vertical" else y
                if abs(coordinate - line["site"]) <= 8:
                    line_near[str(line["id"])] += count
            for block in gaps["Block"]:
                distance = max(block["left"] - x, x - block["right"],
                               block["lower"] - y, y - block["upper"], 0)
                if distance <= 8:
                    block_near[str(block["id"])] += count
        frequencies = {p["Name"]: count for p, count in zip(ports, port_counts) if count}
        result[side] = {
            "port_frequencies": frequencies, "port_count": len(frequencies),
            "tile_coverage": sum(c > 0 for c in tile_counts),
            "tile_frequency_min": min(tile_counts), "tile_frequency_max": max(tile_counts),
            "new_public_ports": {p: c for p, c in frequencies.items() if p not in public[side]},
            "z": z_groups, "spatial_10x25": spatial, "boundary_radius8": edges,
            "corner_radius8": corners, "line_neighborhood_radius8": line_near,
            "block_neighborhood_chebyshev_radius8": block_near,
        }
    result["distance_bands"] = [sum(stats["type_type_band"][i::7]) for i in range(7)]
    result["source_type_target_type_distance"] = stats["type_type_band"]
    result["dx_dy_sign"] = stats["dx_dy_sign"]
    line_cross = collections.Counter()
    lines = [q for q in gaps["Line"] if q["direction"] == "horizontal"]
    lines += [q for q in gaps["Line"] if q["direction"] == "vertical"]
    # Architecture preserves the JSON order separately for each axis.
    for mask, count in stats["line_cross_masks"].items():
        for i, line in enumerate(lines):
            if int(mask) & (1 << i):
                line_cross[str(line["id"])] += count
    block_cross = collections.Counter()
    for mask, count in stats["block_cross_masks"].items():
        for i, block in enumerate(gaps["Block"]):
            if int(mask) & (1 << i):
                block_cross[f"{block['id']}-horizontal"] += count
            if int(mask) & (1 << (7 + i)):
                block_cross[f"{block['id']}-vertical"] += count
    result["line_opposite_sides"] = line_cross
    result["block_opposite_sides"] = block_cross
    adjacent_names = ["same_from_pin", "same_to_pin", "same_from_coordinate",
                      "same_to_coordinate", "same_from_port", "same_to_port"]
    result["adjacent_counts"] = dict(zip(adjacent_names, stats["adjacent"]))
    result["adjacent_ratios"] = {name: count / max(1, stats["rows"] - 1)
                                  for name, count in zip(adjacent_names, stats["adjacent"])}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--dataset", required=True)
    args = parser.parse_args()
    root, dataset = args.root, args.root / args.dataset
    generated = json.loads((dataset / "generation.json").read_text())
    checked = json.loads((dataset / "check/check.json").read_text())
    assert checked["status"] == "passed" and generated["output"] == checked["stats"]
    assert generated["rows"] == checked["unique_rows"] == checked["rows"]
    assert generated["bytes"] == checked["bytes"] == (dataset / "requests.csv").stat().st_size
    for key in ("from_port", "to_port", "from_tile", "to_tile", "type_type_band", "dx_dy_sign",
                "line_cross_masks", "block_cross_masks"):
        assert generated["retained"][key] == generated["output"][key], key
    docs = {p.name: json.loads(p.read_text()) for p in (root / "arch").glob("SRB_*.json")}
    ports = docs["SRB_Port.json"]["Port"]
    tiles = sorted((p["x"], p["y"]) for p in docs["SRB_Inst.json"]["Inst"])
    nets = {p["from"]: p for p in docs["SRB_Net.json"]["Nets"]}
    gaps = docs["SRB_Gap.json"]["Gap"]
    public = json.loads((root / "public-ports.json").read_text())
    output = {
        "version": 1, "status": "frozen", "profile": generated["profile"],
        "rows": generated["rows"], "csv": str((dataset / "requests.csv").resolve()),
        "bytes": generated["bytes"], "sha256": sha256(dataset / "requests.csv"),
        "endpoint_rule": "uniform valid tile and concrete port proposals; reachable; directed unique; From != To",
        "arch_files": [{"name": p.name, "bytes": p.stat().st_size, "sha256": sha256(p)}
                       for p in sorted((root / "arch").glob("SRB_*.json"))],
        "frozen_toolchain": json.loads((root / "toolchain.json").read_text()),
        "proposal_seed": generated["proposal_seed"], "shuffle_seed": generated["shuffle_seed"],
        "label_sample_seed": checked["label_sample_seed"],
        "bootstrap_seed": 2026101502 if generated["profile"] == "U-role" else 2026101501,
        "rng_name_and_version": generated["rng"],
        "shuffle_rule": "two consecutive independent-stream uint64 draws; ascending (high,low,pair); full dataset",
        "shuffle_ties": generated["shuffle_ties"],
        "proposed_rows": generated["proposed_rows"],
        "rejected_self_rows": generated["rejected_self_rows"],
        "rejected_unreachable_rows": generated["rejected_unreachable_rows"],
        "duplicate_proposals": generated["duplicate_proposals"],
        "duplicate_rows": checked["duplicate_rows"], "unique_rows": checked["unique_rows"],
        "dedup_rule": "linear-probed exact uint64 equality, earliest accepted proposal; independent full-key bucket sort",
        "reachability_method_and_identity": {
            "method": "full Net/Arc Z-state SCC, independent forward/reverse BFS, raw-JSON vector walk and endpoint eligibility",
            "graph": json.loads((root / "reach.json").read_text()),
            "index_sha256": sha256(root / "reach.bin"),
            "eligibility_sha256": sha256(root / "independent/eligibility.bin"),
            "geometry": json.loads((root / "independent/geometry.json").read_text()),
            "exact_crosscheck": json.loads((root / "exact-check.json").read_text()),
        },
        "independent_input_check": {
            key: value for key, value in checked.items() if key != "stats"
        },
        "coverage_and_strata": {
            "proposal": summarize(generated["proposed"], ports, tiles, nets, gaps, public),
            "accepted": summarize(generated["output"], ports, tiles, nets, gaps, public),
            "raw_statistics": "generation.json and check/check.json",
            "radius": 8, "spatial_bins": "floor(x/10),floor(y/25)",
            "distance_band_limits": [0, 12, 24, 50, 100, 300, None],
        },
        "label_sample": {
            "path": str((dataset / "check/label-sample.csv").resolve()),
            "sha256": sha256(dataset / "check/label-sample.csv"),
            "rows": checked["label_sample_rows"],
            "method": "per-stratum reservoir sampling, independent mt19937_64 with rejection-modulo integers",
            "status": "unlabelled; overlap with prior training/development requests must be checked before accuracy use",
            "nonzero_quota": 2048 if generated["profile"] == "U-role" else 4096,
            "distance_zero_total_quota": 1024,
        },
        "limits": "fixed official architecture and explicit local distribution; hidden distribution and candidate CPU not verified",
    }
    with (dataset / "manifest.json").open("x") as handle:
        json.dump(output, handle, indent=2)
        handle.write("\n")
    print(json.dumps({key: output[key] for key in ("profile", "rows", "bytes", "sha256")}), flush=True)


if __name__ == "__main__":
    main()
