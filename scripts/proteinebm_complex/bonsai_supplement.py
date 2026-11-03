"""Prepare and run an explicitly approved Bonsai supplement on complete complexes."""
import argparse
import importlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE), str(ROOT), str(ROOT / 'scripts')]
from common import checked, read, sha, write

SCHEMA = 'complex-full-cohort-bonsai-v1'
PACKAGES = ('numpy', 'scipy', 'scikit-learn', 'biopython', 'pandas', 'h5py',
            'tables', 'ruamel.yaml', 'PyYAML', 'psutil', 'matplotlib', 'networkx', 'natsort')


def require_approval(plan_path, approval_path):
    approval = read(approval_path)
    if (approval.get('status') != 'approved' or not approval.get('user_message')
            or approval.get('approved_plan_sha256') != sha(plan_path)):
        raise ValueError('Explicit user approval must bind the exact Bonsai plan')
    plan = read(plan_path)
    if plan['schema'] != SCHEMA or plan['bounds'] != dict(Bonsai_fits=2, UMAP_fits=0,
            HDBSCAN_fits=0, energy_calls=0, TM_calls=0, paid_calls=0, package_installs=0):
        raise ValueError('Unknown Bonsai scientific scope')
    if plan['runtime']['host'] != os.uname().nodename or sys.executable != plan['runtime']['python']:
        raise ValueError('Approved host or interpreter changed')
    checked(Path(sys.executable).resolve(), plan['runtime']['python_sha256'])
    for name, expected in plan['runtime']['versions'].items():
        if version(name) != expected:
            raise ValueError('Approved package changed: ' + name)
    for path, digest in plan['frozen_files'].items():
        checked(path, digest)
    return plan


def prepare(args):
    from scripts.regional_bonsai import inventory
    if args.output.exists():
        raise ValueError('Use a new immutable plan/output directory')
    completed = read(args.review / 'clustering-complete.json')
    files, targets = {}, {}
    tracked = subprocess.check_output(['git', 'ls-files', 'src', 'scripts'], cwd=ROOT, text=True).splitlines()
    scientific = [p for p in tracked if p.endswith('.py') and p != 'scripts/proteinebm_complex/export_atlas.py']
    scientific.append('scripts/proteinebm_complex/bonsai_supplement.py')
    dirty = subprocess.check_output(['git', 'diff', 'HEAD', '--', *scientific], cwd=ROOT, text=True)
    if dirty.strip():
        raise ValueError('Commit scientific source before freezing the plan')
    for name in scientific:
        files[str(ROOT / name)] = sha(ROOT / name)
    for entry in inventory(args.engine):
        files[entry['path']] = entry['sha256']
    files[str(args.review / 'clustering-complete.json')] = sha(args.review / 'clustering-complete.json')
    for target in ('CDK2_DOC1', 'CDK2_DOC1t'):
        row = completed[target]; checked(row['manifest'], row['manifest_sha256'])
        manifest = read(row['manifest']); original = read(args.review / 'payload' / (target+'.json'))
        terminal = manifest['terminal_detection']
        if terminal['retained_reference_positions'] != terminal['reference_positions'] or terminal['excluded_indices']:
            raise ValueError('Bonsai requires the complete original residue mask')
        base = read(args.site / target / 'primary.json')
        if len(base['models']) != 1000 or set(base['models']) != {r['model_id'] for r in original['inputs']}:
            raise ValueError('Published model population differs from original inputs')
        for path in [Path(row['manifest']), args.review / 'payload' / (target+'.json'),
                     *sorted(Path(manifest['distogram_dir']).iterdir()),
                     args.site / target / 'primary.json', args.site / target / 'density.json']:
            if path.is_file():
                files[str(path)] = sha(path)
        targets[target] = dict(manifest=row['manifest'], models=base['models'], residues=original['residues'],
            sequence_sha256=original['sequence_sha256'], source_manifest_sha256=original['source_manifest_sha256'],
            primary_clusters=base['clusters'], feature_count=original['residues']*(original['residues']-1)//2)
    args.output.mkdir(parents=True)
    plan = dict(schema=SCHEMA, source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        branch='codex/cdk2-doc1-proteinebm', frozen_files=files, targets=targets,
        engine=str(args.engine.absolute()), runtime=dict(host=os.uname().nodename, python=sys.executable,
            python_sha256=sha(Path(sys.executable).resolve()), versions={p:version(p) for p in PACKAGES}),
        resources=dict(cpus=8, memory_gib=32, output_gib=2, reserve_gib=50, wall_seconds=14400, gpus=0),
        bounds=dict(Bonsai_fits=2, UMAP_fits=0, HDBSCAN_fits=0, energy_calls=0, TM_calls=0, paid_calls=0, package_installs=0),
        output=str(args.output.absolute()/'analysis'), settings=dict(max_components=None, rescale_by_var=False,
            use_knn=10, zscore_cutoff=1.0, grouping='native tree-path silhouette edge cuts 2–7',
            source_dtype='float16', feature_definition='unchanged complete raw C-alpha pair distances of chains A and B'),
        reuse='One full 1000-model native tree per construct, reused across Primary/HDBSCAN colors; every noise model retained.',
        publication='Add three native Bonsai layouts alongside PCA/UMAP/t-SNE and per-cluster original CIF downloads; preserve coordinates, scores, projections and labels.',
        public_url='https://benavt.github.io/cdk2-doc1-afs3/', automatic_retries=0, api_cost_usd=0,
        approval_required=True)
    write(args.output/'execution-plan.json', plan)
    print(json.dumps(dict(plan=str(args.output/'execution-plan.json'), sha256=sha(args.output/'execution-plan.json'),
                         resources=plan['resources'], bounds=plan['bounds']), indent=2))


def worker(args):
    from run_regional_comparison import require_controller
    require_controller()
    plan = require_approval(args.plan, args.approval_file)
    importlib.import_module('ruamel.yaml')
    import bonsai_clustering as native
    from src.analysis.bonsai_interactive import selected_shared_distance_features, run_ensemble_bonsai
    native.bonsai_submodule_root = lambda: Path(plan['engine'])
    def no_install(executable, status_callback=None):
        checked(Path(executable).resolve(), plan['runtime']['python_sha256'])
        importlib.import_module('ruamel.yaml')
    native._ensure_ruamel_yaml = no_install
    output = Path(plan['output']); output.mkdir(exist_ok=False)
    results = {}
    for target, entry in plan['targets'].items():
        workflow = read(entry['manifest']); names = entry['models']
        matrix, source = selected_shared_distance_features(workflow, names)
        if list(matrix.shape) != [1000, entry['feature_count']]:
            raise ValueError('All-residue Bonsai feature shape differs')
        selected = [dict(model=name, cluster_label=entry['primary_clusters'][i]) for i,name in enumerate(names)]
        tree = run_ensemble_bonsai(matrix, selected, output/target, identifier=target+'_all1000',
                                   feature_source=source, log=print)
        tree['scope'] = ('All 1000 original models of this construct, including HDBSCAN noise. '
                         'Tree geometry is shared by Primary and HDBSCAN views; colors use the selected view. '
                         'B groups are exploratory native tree cuts, not replacements for saved cluster labels.')
        tree['provenance'].update(plan_sha256=sha(args.plan), sequence_sha256=entry['sequence_sha256'],
            source_manifest_sha256=entry['source_manifest_sha256'], residues=entry['residues'])
        path = output/(target+'-bonsai.json'); write(path, tree)
        results[target] = dict(file=str(path), sha256=sha(path), models=1000, residues=entry['residues'])
        del matrix
    write(output/'completion.json', dict(status='validated', plan_sha256=sha(args.plan), targets=results))


def run(args):
    import fcntl
    import psutil
    from run_regional_comparison import monitor, stop_group
    plan = require_approval(args.plan, args.approval_file)
    parent = Path(plan['output']).parent; limits = plan['resources']
    if Path(plan['output']).exists():
        raise ValueError('Inspect the existing output before any recovery; no automatic retry')
    if shutil.disk_usage(parent).free < (limits['reserve_gib']+limits['output_gib'])*2**30:
        raise ValueError('Insufficient free space for output plus reserve')
    with (parent/'controller.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        env = {**os.environ, **{k:'8' for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']},
               'REGIONAL_CONTROLLER_PID':str(os.getpid()), 'PYTHONDONTWRITEBYTECODE':'1', 'CUDA_VISIBLE_DEVICES':''}
        child = None
        try:
            with (parent/'execution.log').open('x') as log, (parent/'resource-telemetry.jsonl').open('x') as telemetry:
                child = subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'run','--plan',str(args.plan),
                    '--approval-file',str(args.approval_file),'--worker'],env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                process = psutil.Process(child.pid)
                process.cpu_affinity(process.cpu_affinity()[:limits['cpus']])
                reason, elapsed = monitor(child,plan,process,psutil,lambda _:shutil.disk_usage(parent),telemetry)
                code = child.wait()
                write(parent/'execution-receipt.json',dict(exit_code=code,stop_reason=reason,elapsed_seconds=elapsed,plan_sha256=sha(args.plan)))
                if code or reason:
                    raise RuntimeError(reason or 'Bonsai failed; preserve diagnostics and inspect before recovery')
        finally:
            if child is not None and child.poll() is None:
                stop_group(child)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p=commands.add_parser('prepare')
    for name in ('review','site','engine','output'):
        p.add_argument('--'+name,type=Path,required=True)
    p=commands.add_parser('run'); p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--approval-file',type=Path,required=True); p.add_argument('--worker',action='store_true')
    args=parser.parse_args()
    if args.command=='prepare': prepare(args)
    elif args.worker: worker(args)
    else: run(args)
