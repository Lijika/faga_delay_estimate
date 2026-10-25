#!/usr/bin/env python3
"""Archive and publish the exact frozen batch-eight ELF after full 1M checks."""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path('validation/results/exp602')


def read(path):
    return json.loads(Path(path).read_text())


def identity(path):
    path = Path(path)
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(8 << 20), b''): digest.update(data)
    return dict(path=str(path), bytes=path.stat().st_size, sha256=digest.hexdigest())


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def package(label):
    assert Path.cwd() == Path('/home/lhjysyx/EDA2026')
    assert label.startswith('exp602-d64-b8-') and '/' not in label and '..' not in label
    archive = Path('subm/versions') / label
    assert not archive.exists(), 'immutable version already exists'
    checked = read(ROOT / 'package-check.json')
    frozen = read('validation/results/exp601/freeze.json')
    scale = read(ROOT / '1b-report.json')
    accuracy = read(ROOT / '1b-accuracy.json')
    binary = Path('build/exp602/estimate')
    program = identity(binary)
    assert checked['all_passed'] and accuracy['goal_accuracy_gate'] and scale['stage_gate']
    assert all(program[k] == frozen['binary'][k] == checked['binary'][k] == scale['binary'][k]
        for k in ('bytes', 'sha256'))
    assert program['bytes'] < 100000000
    deps = subprocess.run(['ldd', str(binary)], capture_output=True, text=True)
    assert 'not a dynamic executable' in deps.stdout + deps.stderr
    assert 'INTERP' not in subprocess.check_output(['readelf', '-l', str(binary)], text=True)
    assert scale['run']['evidence']['contract']['contract_passed']
    assert scale['unique_rows'] == 1000000000 and scale['port_pairs'] == 59904
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    evidence = [Path('validation/results/exp601') / name for name in
        ('freeze.json', 'report.json', '10m-report.json', '100m-report.json')]
    evidence += [ROOT / name for name in ('package-check.json', '1b-report.json', '1b-accuracy.json', 'compiler.txt')]
    evidence += [Path('validation/results/exp601/compile-PQ.run.json'), Path('validation/results/exp588/evaluation.json')]
    archive.mkdir()
    shutil.copy2(binary, archive / 'bin-estimate')
    with zipfile.ZipFile(archive / 'submission.zip', 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.write(archive / 'bin-estimate', 'bin/estimate')
    with zipfile.ZipFile(archive / 'submission.zip') as z:
        assert z.namelist() == ['bin/estimate'] and z.testzip() is None
        assert hashlib.sha256(z.read('bin/estimate')).hexdigest() == program['sha256']
    container = identity(archive / 'submission.zip')
    independent = read('validation/results/exp588/evaluation.json')
    manifest = dict(version_label=label, algorithm_version='D64-R8-batch8-shortcoord', git_commit=head,
        git_working_tree_dirty=True, bin_sha256=program['sha256'], bin_bytes=program['bytes'],
        packaged_utc=datetime.now(timezone.utc).isoformat(),
        build_utc=checked['binary_mtime_utc'],
        compiler=(ROOT / 'compiler.txt').read_text().strip(),
        compile_command=read('validation/results/exp601/compile-PQ.run.json')['command'],
        zip_sha256=container['sha256'], zip_bytes=container['bytes'],
        link_mode='static; five architectures and all model assets embedded',
        evidence=[identity(p) for p in evidence], build_freeze=identity(evidence[0]),
        build_command='cd research/exp601 && PYTHONPATH=../exp554/vendor ../exp491/build/venv/bin/python -B validation/exp601_short_coordinates.py build',
        package_command=f'python3 validation/exp602_package.py {label}',
        cpu_1b_s=scale['run']['cpu_s'], cpu_100m_s=read(evidence[3])['run']['cpu_s'],
        stage_1b_300s_passed=scale['stage_gate'],
        independent_1m_evidence=identity('validation/results/exp588/evaluation.json'),
        independent_1m_accuracy_pp=independent['evidence']['D64']['statistics']['accuracy_pp'],
        scale_1b_accuracy=accuracy['accuracy_pp'], scale_1b_accuracy_ci=accuracy['ci95_accuracy_pp'],
        platform_score_verified=False, full_1b_exact_accuracy_verified=False,
        note='Frozen measured ELF; package preserves its bytes. Ordinary source build remains a separate candidate.')
    write(archive / 'version.json', manifest)
    (archive / 'identities.txt').write_text(
        f"{program['sha256']}  bin-estimate\n{container['sha256']}  submission.zip\n")
    for path in evidence: shutil.copy2(path, archive / path.name)
    assert identity(archive / 'bin-estimate')['sha256'] == program['sha256']
    latest = Path('subm/latest')
    latest.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir='build/exp602', prefix='publish-') as temporary:
        staging = Path(temporary)
        shutil.copy2(archive / 'submission.zip', staging / 'submission.zip')
        shutil.copy2(archive / 'bin-estimate', staging / 'estimate-bin')
        write(staging / 'identity.json', {**manifest, 'immutable_source': str(archive)})
        for name in ('submission.zip', 'estimate-bin', 'identity.json'):
            os.replace(staging / name, latest / name)
    with Path('subm/versions/INDEX.txt').open('a') as stream:
        stream.write(f"{label}  bin={program['sha256']}  zip={container['sha256']}\n")
    shutil.copy2(archive / 'submission.zip', 'subm/submission.zip')
    assert identity('subm/submission.zip')['sha256'] == container['sha256']
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    assert len(sys.argv) == 2
    package(sys.argv[1])
