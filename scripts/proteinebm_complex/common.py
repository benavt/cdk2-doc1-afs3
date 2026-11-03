"""Immutable files and isolated finished whole-job telemetry verification."""
import hashlib
import json
import os
from pathlib import Path
import subprocess


def require(value, message):
    if not value:
        raise ValueError(message)


def physical(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts and
            not any(p.is_symlink() for p in (path, *path.parents)), 'Expected physical absolute path')
    return path


def sha(path):
    h = hashlib.sha256()
    with physical(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def checked(path, expected):
    require(sha(path) == expected, 'Artifact changed: ' + str(path))


def read(path):
    return json.loads(physical(path).read_text())


def write(path, value):
    path = physical(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def finished(attempt, monitor, gpu=False):
    attempt = physical(attempt)
    receipt = read(attempt / 'submission-result.json')
    require(receipt['status'] == 'accepted' and receipt['scheduler_script_verified'],
            'Producer submission was not verified')
    checked(attempt / 'workload.sh', receipt['workload_sha256'])
    runtime = physical(monitor['runtime'])
    checked(runtime / 'manifest.json', monitor['manifest_sha256'])
    for name, digest in read(runtime / 'manifest.json')['sha256'].items():
        require(not Path(name).is_absolute() and '..' not in Path(name).parts, 'Unsafe runtime member')
        checked(runtime / name, digest)
    logs = list((attempt / 'resources').glob('*.log'))
    require(len(logs) == 1, 'Exactly one non-requeued resource log required')
    rows = [json.loads(line[len('[resource] '):]) for line in logs[0].read_text().splitlines()
            if line.startswith('[resource] {')]
    starts = [r for r in rows if r.get('event') == 'start']
    exits = [r for r in rows if r.get('event') == 'command_exit']
    summaries = [r for r in rows if r.get('event') == 'summary']
    require(len(starts) == len(exits) == len(summaries) == 1 and exits[0]['exit_code'] == 0,
            'Producer did not finish successfully')
    require(str(starts[0]['job']) == str(receipt['job_id']) and
            starts[0]['device'] == ('mixed' if gpu else 'cpu'), 'Producer device/identity mismatch')
    env = {k: v for k, v in os.environ.items() if not k.startswith('PYTHON') and
           k not in {'FLEET_MASK_RECIPE', 'FLEET_MASK_INDEX'}}
    require(not env.get('FLEET_RESOURCE_CHECK_ACTIVE'), 'Recursive checker refused')
    env['FLEET_RESOURCE_CHECK_ACTIVE'] = '1'
    argv = [monitor['python'], '-I', str(runtime / 'check_log.py'), str(logs[0]), '--finished']
    if gpu:
        argv.append('--gpu')
    result = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=60)
    require(result.returncode == 0, 'Incomplete resource evidence: ' + result.stdout + result.stderr)
    return {'job_id': receipt['job_id'], 'log_sha256': sha(logs[0])}
