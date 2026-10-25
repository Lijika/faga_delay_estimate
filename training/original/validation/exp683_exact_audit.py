#!/usr/bin/env python3
"""Verify repeated exact requests agree across the old and expanded samples."""
import csv
from pathlib import Path
import socket
import sys
import tempfile

import exp683_expanded_exact as sample


def compare(old_path, new_path):
    with old_path.open(newline='') as stream:
        old = {(r['from'], r['to']): int(r['exact']) for r in csv.DictReader(stream)}
    overlap = checked = 0
    with new_path.open(newline='') as stream:
        for row in csv.DictReader(stream):
            key = row['from'], row['to']
            value = int(row['exact'])
            assert value >= 0
            if key in old:
                assert value == old[key], (key, value, old[key])
                overlap += 1
            checked += 1
    return dict(expanded_rows=checked, old_unique_rows=len(old), overlap_rows=overlap,
                repeated_exact_values_equal=True)


def self_check():
    with tempfile.TemporaryDirectory() as directory:
        old, new = (Path(directory)/name for name in ('old.csv','new.csv'))
        old.write_text('from,to,exact\na,b,0\nc,d,23\n')
        new.write_text('from,to,exact\nc,d,23\na,b,0\ne,f,5\n')
        assert compare(old,new) == dict(expanded_rows=3,old_unique_rows=2,
            overlap_rows=2,repeated_exact_values_equal=True)
        new.write_text('from,to,exact\nc,d,24\n')
        try:
            compare(old,new)
        except AssertionError:
            return dict(passed=True,matching_labels=True,zero_delay=True,mismatch_rejected=True)
        raise AssertionError('mismatched exact label was accepted')


def main(case):
    checked = self_check()
    root = Path('validation/results/exp683')/case
    report = sample.read(root/'report.json')
    inputs = sample.read(root/'input.json')
    assert report['all_complete_label_checks'] and report['span_checks'] == 12
    if case == '100m':
        old_root = Path('../exp679')
        old_report = sample.read(old_root/'validation/results/exp679/report.json')
        assert old_report['all_complete_label_checks']
        old_path = old_root/old_report['exact']['path']
    else:
        old_root = Path('../exp580')
        old_report = sample.read(old_root/'validation/results/exp580/offline-label-report.json')
        assert old_report['all_complete']
        old_path = old_root/'build/exp580/scale-exact.csv'
    new_path = Path(report['exact']['path'])
    for path, identity in ((old_path,old_report['exact']),(new_path,report['exact'])):
        sample.check(path,identity)
    result = compare(old_path,new_path)
    assert result['expanded_rows'] == report['rows'] == sample.CASES[case][1]*59904
    assert result['overlap_rows'] == inputs['old_sample_overlap']
    assert all(r['exit_code'] == 0 for r in report['runs'])
    assert all(r['rss_bytes'] <= 2_000_000_000 for r in report['runs'])
    cpu = sum(r['cpu_s'] for r in report['runs'])
    assert cpu <= sample.CASES[case][3]
    target = root/'independent-exact-audit.json'
    assert not target.exists()
    sample.write(target,dict(**result,self_check=checked,source=sample.identity(__file__),
        old_exact=sample.identity(old_path),expanded_exact=sample.identity(new_path),
        span_checks=report['span_checks'],label_cpu_s=cpu,
        label_max_rss_bytes=max(r['rss_bytes'] for r in report['runs']),
        complete_estimator_runs=0,accuracy_not_read=True))
    print('EXP683_EXACT_OVERLAP_VERIFIED',case,result,flush=True)


if __name__ == '__main__':
    assert socket.gethostname() == 'lhj-R4900-G3'
    assert Path.cwd() == Path('/home/lhj/lhjwork/eda2026/research/exp683')
    assert len(sys.argv) == 2 and sys.argv[1] in sample.CASES
    main(sys.argv[1])
