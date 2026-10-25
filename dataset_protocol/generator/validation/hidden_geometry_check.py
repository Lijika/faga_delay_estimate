#!/usr/bin/env python3
"""Independently interpret raw JSON geometry and emit endpoint eligibility."""
import argparse
import json
import struct
from pathlib import Path

import numpy as np


def read_vector(handle, dtype):
    size = struct.unpack("<Q", handle.read(8))[0]
    raw = handle.read(size * np.dtype(dtype).itemsize)
    assert len(raw) == size * np.dtype(dtype).itemsize
    return np.frombuffer(raw, dtype=dtype).copy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--arch", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    docs = {p.name: json.loads(p.read_text()) for p in args.arch.glob("SRB_*.json")}
    ports = docs["SRB_Port.json"]["Port"]
    port_id = {p["Name"]: i for i, p in enumerate(ports)}
    tiles = sorted((p["x"], p["y"]) for p in docs["SRB_Inst.json"]["Inst"])
    assert len(ports) == 496 and len(tiles) == len(set(tiles)) == 60200
    x = np.array([p[0] for p in tiles], dtype=np.int32)
    y = np.array([p[1] for p in tiles], dtype=np.int32)
    tile_at = np.full((550, 120), -1, dtype=np.int32)
    tile_at[y, x] = np.arange(len(tiles))
    gaps = docs["SRB_Gap.json"]["Gap"]
    blocks = gaps["Block"]
    assert len(blocks) == 7
    block_at = np.full((550, 120), -1, dtype=np.int32)
    for i, b in enumerate(blocks):
        block_at[b["lower"]:b["upper"] + 1, b["left"]:b["right"] + 1] = i

    # This walk reads only JSON rectangles and does not call Architecture.
    def resolve(dx, dy):
        assert (dx == 0) != (dy == 0)
        cx, cy = x.copy(), y.copy()
        remaining = np.full(len(tiles), abs(dx or dy), dtype=np.int32)
        valid = np.ones(len(tiles), dtype=bool)
        horizontal = dx != 0
        sx, sy = (dx > 0) - (dx < 0), (dy > 0) - (dy < 0)
        while np.any(valid & (remaining > 0)):
            active = valid & (remaining > 0)
            cx[active] += sx
            cy[active] += sy
            valid &= (cx >= 0) & (cx < 120) & (cy >= 0) & (cy < 550)
            active &= valid
            ids = np.flatnonzero(active)
            b_ids = block_at[cy[ids], cx[ids]]
            consume = np.ones(len(ids), dtype=bool)
            for i, b in enumerate(blocks):
                if b["horizontal crossable" if horizontal else "vertical crossable"]:
                    consume[b_ids == i] = False
            remaining[ids[consume]] -= 1
        dest = np.full(len(tiles), -1, dtype=np.int32)
        ids = np.flatnonzero(valid)
        dest[ids] = tile_at[cy[ids], cx[ids]]
        return dest

    nets = docs["SRB_Net.json"]["Nets"]
    z_ports = [port_id[n["from"]] for n in nets]
    net_by_z = {port_id[n["from"]]: n for n in nets}
    z_id = {p: i for i, p in enumerate(z_ports)}
    assert len(z_ports) == 160
    with args.index.open("rb") as handle:
        assert handle.read(8) == b"HREACH01"
        cells = read_vector(handle, "<u4")
        component = read_vector(handle, "<u4").reshape(len(tiles), 160)
        predecessor = read_vector(handle, "<u4").reshape(len(tiles), 160)
        sizes = read_vector(handle, "<u4")
        dag = read_vector(handle, "<u8")
        assert handle.read() == b""
    assert np.array_equal(cells, y * 120 + x)
    core = int(np.argmax(sizes))
    assert np.all(dag >> np.uint64(32) == core)
    geometry = {}
    net_valid = np.zeros((len(tiles), 160), dtype=bool)
    hops = 0
    for zi, port in enumerate(z_ports):
        net = net_by_z[port]
        offset = net["delta x"], net["delta y"]
        if offset not in geometry:
            geometry[offset] = resolve(*offset)
        dest = geometry[offset]
        good = dest >= 0
        assert np.array_equal(component[:, zi] == core, good)
        expected = np.full(len(tiles), np.uint32(0xffffffff), dtype=np.uint32)
        expected[dest[good]] = np.flatnonzero(good) * 160 + zi
        assert len(set(dest[good].tolist())) == int(good.sum())
        assert np.array_equal(predecessor[:, zi], expected)
        net_valid[:, zi] = good
        hops += int(good.sum())
    assert hops == int(sizes[core]) == 9417280
    source = np.zeros((len(tiles), 496), dtype=np.uint8)
    target = np.zeros_like(source)
    direct = np.zeros((496, 496), dtype=np.uint8)
    source[:, z_ports] = net_valid
    target[:, z_ports] = 1
    arcs = docs["SRB_Arc.json"]["Arcs"]
    net_by_i = {port_id[n["to"]]: z_id[port_id[n["from"]]] for n in nets}
    for a in arcs:
        f, t = port_id[a["from"]], port_id[a["to"]]
        direct[f, t] = 1
        if f not in z_id and ports[f]["Name"][0] in "AS" and t in z_id:
            source[:, f] |= net_valid[:, z_id[t]]
        if ports[t]["Name"][0] in "AS" and ports[t]["Direction"] == "Output" and f in net_by_i:
            target[:, t] |= predecessor[:, net_by_i[f]] != np.uint32(0xffffffff)
    from_ports = sorted(set(z_ports) | {
        port_id[a["from"]] for a in arcs if a["from"][0] in "AS"
    })
    to_ports = [i for i, p in enumerate(ports) if p["Direction"] == "Output"]
    assert len(from_ports) == 208 and len(to_ports) == 288
    args.out.mkdir(exist_ok=False)
    with (args.out / "eligibility.bin").open("xb") as handle:
        handle.write(b"HEQUAL01")
        cells.tofile(handle)
        source.tofile(handle)
        target.tofile(handle)
        direct.tofile(handle)
    report = {
        "status": "passed", "net_hops": hops, "unique_offsets": len(geometry),
        "forward_geometry_and_predecessor_all_states": True,
        "from_port_ids": from_ports, "to_port_ids": to_ports,
        "ports": ports, "source_eligible_per_port": source.sum(axis=0).tolist(),
        "target_eligible_per_port": target.sum(axis=0).tolist(),
        "label_sample_seed": 2026101401,
    }
    (args.out / "geometry.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("status", "net_hops", "unique_offsets")}))


if __name__ == "__main__":
    main()
