"""Freeze a local review package; never connect, submit jobs, or fit models."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from common import sha, write
from worker import SETTINGS

RESOURCES = {
    'prepare': dict(cpus=2, memory_gib=16, wall_minutes=45, gpus=0),
    'pilot': dict(cpus=4, memory_gib=64, wall_minutes=10, gpus=1),
    'gate': dict(cpus=1, memory_gib=4, wall_minutes=10, gpus=0),
    'production': dict(cpus=4, memory_gib=64, wall_minutes=90, gpus=1),
    'accept': dict(cpus=2, memory_gib=8, wall_minutes=20, gpus=0),
}


def parse_inventory(path):
    records = [json.loads(line) for line in Path(path).read_text().splitlines()]
    if not records or records[-1] != {'kind': 'complete', 'models': 2000}:
        raise ValueError('Inventory did not complete')
    targets = {}
    for record in records[:-1]:
        if record['kind'] == 'target':
            target = record['target']
            if target in targets:
                raise ValueError('Duplicate target inventory')
            targets[target] = {**record, 'inputs': []}
        elif record['kind'] == 'model':
            targets[record['target']]['inputs'].append(record)
        else:
            raise ValueError('Unexpected inventory record')
    if set(targets) != {'CDK2_DOC1', 'CDK2_DOC1t'}:
        raise ValueError('Unexpected targets')
    for target, data in targets.items():
        rows = data['inputs']
        if len(rows) != 1000 or {(r['seed'], r['sample']) for r in rows} != {
                (seed, sample) for seed in range(1, 201) for sample in range(5)}:
            raise ValueError('Incomplete seed/sample inventory')
        if [(r['seed'], r['sample']) for r in rows] != sorted((r['seed'], r['sample']) for r in rows):
            raise ValueError('Model order must be seed then sample')
        if len({r['path'] for r in rows}) != 1000 or any(
                r['model_id'] != f'{target}__afsample3__{i:04d}' for i, r in enumerate(rows)):
            raise ValueError('Duplicate source or inconsistent canonical identity')
        if [c['id'] for c in data['chains']] != ['A', 'B']:
            raise ValueError('Expected explicitly named CDK2 and DOC1 chains')
    return targets


def prepare(args):
    if args.output.exists():
        raise ValueError('Use a new immutable preparation directory')
    dirty = subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain', '--',
                                      'src', 'scripts', 'config'], text=True)
    if dirty.strip():
        raise ValueError('Commit source before freezing a scientific execution plan')
    commit = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    targets = parse_inventory(args.inventory)
    binding = json.loads(args.engine_binding.read_text())
    engine = binding['runs']['scoring']
    parent = json.loads(args.native_manifest.read_text())
    native_source = str(Path(binding['runs']['sampling']['recipe']['path']).parent / 'native')
    native_files = {name[len('native/'):]: digest for name, digest in parent['payload_sha256'].items()
                    if name.startswith('native/')}
    if not native_files:
        raise ValueError('Complete frozen native source manifest required')
    proteinebm_host = os.environ.get('PROTEINEBM_HOST')
    if not proteinebm_host:
        raise ValueError('PROTEINEBM_HOST environment variable is required')
    monitor = json.loads(args.monitor.read_text())['machines'][proteinebm_host]
    payload = args.output / 'payload'; payload.mkdir(parents=True)
    for name in ('common.py', 'features.py', 'worker.py'):
        shutil.copyfile(HERE / name, payload / name)
    payload_hashes = {p.name: sha(p) for p in payload.iterdir()}
    root = args.remote_root
    commands, summaries = [], {}
    for target, data in targets.items():
        destination = root / target
        sequence = ''.join(c['sequence'] for c in data['chains'])
        source_digest = hashlib.sha256(json.dumps(data['inputs'], sort_keys=True,
                                                  separators=(',', ':')).encode()).hexdigest()
        plan = dict(schema='proteinebm-complex-1000-v1', run_id=args.run_id, target=target,
                    run_root=str(destination), chains=data['chains'], models=1000,
                    residues=len(sequence), sequence_sha256=hashlib.sha256(sequence.encode()).hexdigest(),
                    input_json_sha256=data['input_sha256'], source_manifest_sha256=source_digest,
                    inputs=data['inputs'], settings=SETTINGS, checkpoint=engine['checkpoint'],
                    config=engine['config'], python=binding['deployment']['python'],
                    native_source=native_source, native_files=native_files, monitor=monitor,
                    payload_sha256=payload_hashes,
                    attempts={phase: str(destination / 'receipts' /
                              f'{args.run_id[:10]}_{phase}_001') for phase in RESOURCES})
        write(payload / (target + '.json'), plan)
        summaries[target] = dict(models=1000, residues=len(sequence),
            chains=[dict(id=c['id'], residues=len(c['sequence']), description=c.get('description'))
                    for c in data['chains']], sequence_sha256=plan['sequence_sha256'],
            source_manifest_sha256=source_digest, plan_sha256=sha(payload / (target + '.json')))
        for phase, resources in RESOURCES.items():
            script = payload / f'{target}-{phase}.sbatch'
            command = [plan['python'], '-I', str(root / 'payload/worker.py'), phase,
                       '--plan', str(root / 'payload' / (target + '.json')),
                       '--plan-sha256', sha(payload / (target + '.json'))]
            minutes = resources['wall_minutes']
            slurm_partition = os.environ.get('PROTEINEBM_SLURM_PARTITION')
            if not slurm_partition:
                raise ValueError('PROTEINEBM_SLURM_PARTITION environment variable is required')
            body = ('#!/bin/bash\n'
                    f'#SBATCH --job-name={target}-ProteinEBM-{phase}\n'
                    f'#SBATCH --partition={slurm_partition}\n#SBATCH --nodes=1\n#SBATCH --ntasks=1\n'
                    f'#SBATCH --cpus-per-task={resources["cpus"]}\n'
                    f'#SBATCH --mem={resources["memory_gib"]}G\n'
                    f'#SBATCH --time={minutes//60:02d}:{minutes%60:02d}:00\n'
                    '#SBATCH --nice=0\n#SBATCH --no-requeue\n'
                    + ('#SBATCH --gres=gpu:1\n' if resources['gpus'] else '')
                    + 'set -euo pipefail\n'
                    + 'export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1\n'
                    + ('export CUDA_VISIBLE_DEVICES=""\n' if not resources['gpus'] else '')
                    + 'export PYTHONNOUSERSITE=1\nexec ' + shlex.join(command) + '\n')
            script.write_text(body)
            subprocess.run(['bash', '-n', str(script)], check=True)
            argv = [str(args.fleet_home / 'scripts/fleet.py'), 'submit', proteinebm_host, '--script', str(root / 'payload' / script.name),
                    '--attempt', plan['attempts'][phase], '--cwd', str(destination),
                    '--device', 'gpu' if resources['gpus'] else 'cpu', '--no-notify']
            if resources['gpus']:
                argv.extend(['--workload-kind', 'analysis'])
            commands.append(dict(target=target, phase=phase, argv=argv,
                                 afterok_phase={'pilot': 'prepare', 'gate': 'pilot',
                                                'production': 'gate', 'accept': 'production'}.get(phase),
                                 apply=False, script_sha256=sha(script)))
    source_names = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files', 'src', 'scripts', 'config', 'pyproject.toml', 'project_support.py'],
                                            text=True).splitlines()
    sources = {name: sha(ROOT / name) for name in source_names}
    write(args.output / 'source-manifest.json', sources)
    clustering_host = os.environ.get('PROTEINEBM_CLUSTERING_HOST', proteinebm_host)
    plan = dict(schema_version=1, run_id=args.run_id, branch='codex/cdk2-doc1-proteinebm',
                source_commit=commit, source_manifest_sha256=sha(args.output / 'source-manifest.json'),
                input_inventory_sha256=sha(args.inventory), targets=summaries,
                remote_root=str(root), scoring_settings=SETTINGS, resources=RESOURCES,
                scientific_jobs=10, maximum_simultaneous_GPUs=2, maximum_GPU_hours=10/3,
                energy_values=32000, native_GPU_batch_calls=2240,
                CPU_process_budget='One native process per job; production has one controller and one native child; one numerical thread per native worker',
                priority='nice=0; request highest ordinary account priority; verify effective queue order without changing other jobs',
                automatic_retries=0, paid_external_calls=0, external_cost_usd=0,
                clustering=dict(host=clustering_host, models_per_target=1000, separate_constructs=True,
                    mask='all residues of chains A and B; no terminal trimming or user exclusions',
                    terminal_config_sha256=sha(ROOT / 'config/terminal_variance_all_residues.json'),
                    methods=['raw CA distance features', 'PCA', 'UMAP', 't-SNE',
                             'validated UMAP component/subdivision cluster labels'],
                    cpus=8, memory_gib=32, wall_hours_cap=12,
                    total_local_intake_and_output_gib_cap=3, free_space_reserve_gib=50,
                    local_python=args.local_python,
                    identifier_template=args.run_id + '_{target}',
                    output_parent=str(ROOT / 'data/processed'),
                    all_residue_verification='Reject any lost chain/residue before fitting; verify retained count and shared-residue mask after workflow'),
                publication=dict(provider='GitHub Pages', proposed_new_repository='benavt/cdk2-doc1-afs3',
                    existing_public_sites_modified=False, public_models=2000,
                    color_field='ProteinEBM energy at t=0.10 (full construct)',
                    plot_methods=['PCA', 'UMAP', 't-SNE'],
                    contents=['two target views', 'cluster labels', 'original model coordinates',
                              'AFS3 confidence annotations', 'ProteinEBM t=0.10 numeric colors'],
                    private_receipts_and_host_paths_public=False,
                    status='Candidate to be built and inspected after accepted scientific results'),
                status='prepared_awaiting_explicit_execution_approval')
    write(args.output / 'execution-plan.json', plan)
    write(args.output / 'submission-commands.json', commands)
    print(json.dumps(dict(plan=str(args.output / 'execution-plan.json'),
                         sha256=sha(args.output / 'execution-plan.json'), source_commit=commit,
                         targets=summaries, jobs=10), indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inventory', type=Path, required=True)
    p.add_argument('--engine-binding', type=Path, required=True)
    p.add_argument('--native-manifest', type=Path, required=True)
    p.add_argument('--monitor', type=Path, required=True)
    p.add_argument('--fleet-home', type=Path, required=True)
    p.add_argument('--run-id', required=True)
    p.add_argument('--remote-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--local-python', required=True)
    prepare(p.parse_args())


if __name__ == '__main__':
    main()
