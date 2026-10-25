def dataset():
    frozen = fresh.freeze_check()
    proposal = BUILD / "proposal"
    speed.measured([str(HIDDEN / "make_hidden_suite"), str(fresh.ARCH), str(HIDDEN / "reach.bin"),
        "U-role", str(frozen["proposal_rows"]), str(frozen["proposal_seed"]),
        str(frozen["shuffle_seed"]), str(proposal)], "generate-proposal")
    training = Path("../exp501/build/exp501/u-role/requests.csv")
    with training.open("rb") as stream:
        assert stream.readline() == b"From,To\n"
        source_pins = {line.split(b",", 1)[0] for line in stream}
    known = set()
    for item in frozen["history"]:
        path = Path(item["path"])
        check(path, item)
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", newline="") as stream:
            reader = csv.DictReader(stream)
            a, b = ("From", "To") if "From" in reader.fieldnames else ("from", "to")
            for row in reader:
                if row[a].encode() not in source_pins:
                    known.add((row[a] + "," + row[b]).encode())
    generated = BUILD / "u-role"
    generated.mkdir()
    request = generated / "requests.csv"
    with (proposal / "requests.csv").open("rb") as source, request.open("xb") as output:
        population, sample, filtering = fresh.filter_stream(source, output, source_pins, known,
            frozen["source_ports"], frozen["target_ports"], ROWS)
    source_count, history_count = len(source_pins), len(known)
    del source_pins, known
    speed.measured([str(HIDDEN / "check_hidden_suite"), str(fresh.ARCH), str(HIDDEN / "reach.bin"),
        str(HIDDEN / "independent/eligibility.bin"), "U-role", str(ROWS), str(request),
        str(generated / "check")], "input-check")
    checked = read(generated / "check/check.json")
    assert checked["status"] == "passed" and checked["unique_rows"] == ROWS
    write(ROOT / "100m-input.json", dict(input=identity(request), rows=ROWS, unique_rows=ROWS,
        port_pairs=59904, proposal=identity(proposal / "requests.csv"), filtering=filtering,
        training_source_pins=source_count, historical_pairs_after_source_filter=history_count,
        source_pin_overlap=0, registered_history_overlap=0, history=frozen["history"],
        minimum_pair_rows=min(population), maximum_pair_rows=max(population),
        independent_checker=identity(generated / "check/check.json")))
    write(BUILD / "pair-populations.json", population)
    print("EXP685_POPULATION_COMPLETE", flush=True)
