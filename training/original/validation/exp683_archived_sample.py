#!/usr/bin/env python3
"""Extract positions while verifying the complete decompressed exp655 output."""
import hashlib
import io
from pathlib import Path
import subprocess
import time

import numpy as np

import exp683_expanded_exact as sample


def stream_sample(source, output, positions, rows, expected, block_bytes=16<<20):
    assert positions.ndim == 1 and len(positions) and positions[0] >= 0
    assert positions[-1] < rows and np.all(np.diff(positions) > 0)
    digest, size, count, selected = hashlib.sha256(), 0, 0, 0
    carry, header = b'', False
    output.write(b'row,From,To,delay\n')
    for block in iter(lambda:source.read(block_bytes),b''):
        digest.update(block)
        size += len(block)
        lines = (carry+block).split(b'\n')
        carry = lines.pop()
        if not header and lines:
            assert lines.pop(0) == b'From,To,delay'
            header = True
        end = count+len(lines)
        stop = int(np.searchsorted(positions,end))
        for position in positions[selected:stop]:
            output.write(str(int(position)).encode()+b','+lines[int(position)-count]+b'\n')
        selected, count = stop, end
    assert header and carry == b'' and count == rows and selected == len(positions)
    actual = dict(bytes=size,sha256=digest.hexdigest())
    assert all(actual[k] == expected[k] for k in actual),actual
    return dict(rows=count,sample_rows=selected,uncompressed=actual,complete_sha_verified=True)


def self_check():
    original = b'From,To,delay\na,b,0\nc,d,17\ne,f,2\ng,h,13\n'
    expected = dict(bytes=len(original),sha256=hashlib.sha256(original).hexdigest())
    for size in (1,2,7,16,1024):
        output = io.BytesIO()
        result = stream_sample(io.BytesIO(original),output,np.array([0,2,3]),4,expected,size)
        assert result['complete_sha_verified']
        assert output.getvalue() == b'row,From,To,delay\n0,a,b,0\n2,e,f,2\n3,g,h,13\n'
    for invalid in (original[:-1],original.replace(b'17',b'18'),original+b'x,y,1\n'):
        try:
            stream_sample(io.BytesIO(invalid),io.BytesIO(),np.array([0,3]),4,expected,7)
        except AssertionError:
            continue
        raise AssertionError('invalid decompressed output accepted')
    return dict(passed=True,chunk_sizes=[1,2,7,16,1024],zero_delay=True,
                missing_newline_rejected=True,sha_mismatch_rejected=True,trailing_rows_rejected=True)


def extract(output_path, sampled, positions, report, root):
    started, cpu = time.monotonic(), time.process_time()
    archive_record = Path('../exp663/validation/results/exp663/prior-output-archive-verified.json')
    archived = sample.read(archive_record)
    archive = output_path.with_suffix(output_path.suffix+'.zst')
    assert archived['full_uncompressed_sha_verified'] and report['contract']['contract_passed']
    assert report['contract']['rows'] == report['rows']
    assert all(archived['source'][k] == report['output'][k] for k in ('bytes','sha256'))
    sample.check(archive,archived['archive'])
    result = self_check()
    command = ['zstd','-d','-q','-c',str(archive)]
    help_text = subprocess.check_output(['zstd','--help'],text=True)
    assert 'decompression' in help_text and 'force write to standard output' in help_text
    (root/'archive-zstd-help.txt').write_text(help_text)
    sample.write(root/'archive-extraction-freeze.json',dict(self_check=result,
        source=sample.identity(__file__),archive_record=sample.identity(archive_record),
        archive=archived['archive'],uncompressed=report['output'],command=command,
        prior_contract=report['contract'],sampled=str(sampled),new_estimator_runs=0))
    with sampled.open('xb') as target, (root/'archive-decompression.stderr').open('xb') as err:
        process = subprocess.Popen(command,stdout=subprocess.PIPE,stderr=err)
        try:
            result = stream_sample(process.stdout,target,positions,report['rows'],report['output'])
            process.stdout.close()
            assert process.wait(timeout=120) == 0
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=120)
    assert not (root/'archive-decompression.stderr').read_bytes()
    contract = dict(report['contract'],sample_rows=len(positions),
        reused_after_complete_sha_verification=True)
    evidence = dict(command=command,exit_code=0,stream=result,sample=sample.identity(sampled),
        wall_s=time.monotonic()-started,driver_cpu_s=time.process_time()-cpu,
        complete_estimator_runs=0,contract_reused_from_same_bytes=True)
    sample.write(root/'archive-extraction.json',evidence)
    return evidence,contract
