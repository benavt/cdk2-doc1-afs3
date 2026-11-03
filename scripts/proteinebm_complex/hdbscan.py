"""Prepare or explicitly execute whole-cohort 10D UMAP/HDBSCAN on saved features."""
import argparse
import hashlib
import importlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
from common import checked, read, sha, write

SETTINGS = dict(seeds=[42, 7, 123], n_neighbors=30, min_dist=0.0,
                min_cluster_size=15, min_samples=11, workers=8)
PACKAGES = ('numpy', 'scipy', 'scikit-learn', 'umap-learn', 'numba')


def prepare(args):
    if args.output.exists():
        raise ValueError('Use a new immutable plan directory')
    original = read(args.review / 'execution-plan.json')
    completed = read(args.review / 'clustering-complete.json')
    sources = subprocess.check_output(['git', 'ls-files', 'src', 'scripts/casp17_hdbscan.py',
                                      'scripts/proteinebm_complex/hdbscan.py'], cwd=ROOT, text=True).splitlines()
    sources = [name for name in sources if name.endswith('.py')]
    dirty = subprocess.check_output(['git', 'status', '--porcelain', '--', *sources], cwd=ROOT, text=True)
    if dirty.strip():
        raise ValueError('Commit scientific Python source before freezing a plan')
    native_names = ['hd_density_experiment.py', 'hierarchical_colors.py']
    changed = subprocess.check_output(['git', 'status', '--porcelain', '--',
        *['src/analysis/' + name for name in native_names]], cwd=args.density_source, text=True)
    if changed.strip():
        raise ValueError('Native HDBSCAN source is dirty')
    native_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=args.density_source, text=True).strip()
    files = {str(ROOT / name): sha(ROOT / name) for name in sources}
    targets = {}
    for target, row in completed.items():
        checked(row['manifest'], row['manifest_sha256'])
        workflow = read(row['manifest'])
        terminal = workflow['terminal_detection']
        if terminal['retained_reference_positions'] != terminal['reference_positions'] or terminal['excluded_indices']:
            raise ValueError('This plan requires every original residue')
        parent = args.review / 'payload' / (target + '.json')
        for path in [Path(row['manifest']), parent, *sorted(Path(workflow['distogram_dir']).iterdir())]:
            if path.is_file():
                files[str(path)] = sha(path)
        model_plan = read(parent)
        names = [r['model_id'] for r in model_plan['inputs']]
        targets[target] = dict(models=names, manifest=row['manifest'], manifest_sha256=row['manifest_sha256'],
            source_manifest_sha256=model_plan['source_manifest_sha256'], residues=model_plan['residues'],
            sequence_sha256=model_plan['sequence_sha256'])
    args.output.mkdir(parents=True)
    native = args.output / 'native'; native.mkdir()
    for name in native_names:
        shutil.copyfile(args.density_source / 'src/analysis' / name, native / name)
        files[str(native / name)] = sha(native / name)
    plan = dict(schema='complex-whole-cohort-hdbscan-v1', run_id=args.output.name,
        parent_run=original['run_id'], source_commit=subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), branch='codex/cdk2-doc1-proteinebm',
        source_root=str(ROOT), parent_review=str(args.review), targets=targets, settings=SETTINGS,
        dimension=10, native_source=str(native), native_commit=native_commit,
        frozen_files=files, runtime=dict(host=os.uname().nodename, python=sys.executable,
            python_sha256=sha(Path(sys.executable).resolve()), versions={p: version(p) for p in PACKAGES}),
        scientific_output=str(args.output / 'analysis'), resources=dict(cpus=8, memory_gib=32,
            wall_hours_cap=2, output_gib_cap=1, free_space_reserve_gib=50, gpus=0),
        maximum_UMAP_fits=6, maximum_HDBSCAN_extractions=12, paid_external_calls=0,
        automatic_retries=0, primary='seed-42 10D UMAP with leaf HDBSCAN; noise retained',
        diagnostics='seeds 7 and 123; EOM extraction for all three seeds',
        inference_scope='All 1000 models separately for each construct; no recursive refinement',
        presentation='Separate HDBSCAN view on unchanged saved PCA/UMAP/t-SNE maps; existing labels and ProteinEBM scores retained',
        output_url='https://benavt.github.io/cdk2-doc1-afs3/', status='prepared_awaiting_execution_approval')
    write(args.output / 'execution-plan.json', plan)
    print(json.dumps(dict(plan=str(args.output / 'execution-plan.json'),
                         sha256=sha(args.output / 'execution-plan.json'),
                         models=2000, UMAP_fits=6, HDBSCAN_extractions=12, resources=plan['resources']), indent=2))


def run(args):
    import numpy as np
    checked(args.plan, args.plan_sha256)
    plan = read(args.plan)
    if plan['schema'] != 'complex-whole-cohort-hdbscan-v1' or plan['settings'] != SETTINGS:
        raise ValueError('Unknown or changed density settings')
    if plan['runtime']['host'] != os.uname().nodename or sys.executable != plan['runtime']['python']:
        raise ValueError('Execution host/interpreter changed')
    checked(Path(sys.executable).resolve(), plan['runtime']['python_sha256'])
    for package, expected in plan['runtime']['versions'].items():
        if version(package) != expected:
            raise ValueError('Native package version changed: ' + package)
    for path, digest in plan['frozen_files'].items():
        checked(path, digest)
    output = Path(plan['scientific_output'])
    if output.exists():
        raise ValueError('Scientific output already exists; inspect before another run')
    output.mkdir()
    namespace = types.ModuleType('_complex_hdbscan_native')
    namespace.__path__ = [plan['native_source']]
    sys.modules[namespace.__name__] = namespace
    native = importlib.import_module(namespace.__name__ + '.hd_density_experiment')
    from src.analysis.saved_features import materialize
    results = {}
    for target, entry in plan['targets'].items():
        workflow = read(entry['manifest']); names = entry['models']
        features = materialize(workflow, names)
        if features.shape != (1000, entry['residues'] * (entry['residues']-1)//2) or not np.isfinite(features).all():
            raise ValueError('All-residue feature population differs')
        folder = output / target; folder.mkdir()
        proof = dict(shape=list(features.shape), dtype=str(features.dtype),
                     sha256=hashlib.sha256(features.tobytes()).hexdigest(),
                     mask_sha256=workflow['terminal_detection']['pair_mask_sha256'])
        native.fit_selection(features, names, np.arange(1000), 10, SETTINGS, folder / 'fits', print)
        with np.load(folder / 'fits/leaf-seed-42.npz', allow_pickle=False) as saved:
            raw, strength = saved['labels'], saved['probabilities']
        labels, count = native.named_children(raw, names, 'H')
        result = dict(target=target, models=names, labels=labels, clusters=count,
            noise_models=int(np.sum(raw == -1)), membership_strength=strength.tolist(),
            source_manifest_sha256=entry['source_manifest_sha256'], sequence_sha256=entry['sequence_sha256'],
            residues=entry['residues'], plan_sha256=args.plan_sha256, feature_proof=proof,
            diagnostics=read(folder / 'fits/result.json'),
            display='Existing 2D PCA/UMAP/t-SNE projections; inference used fresh 10D UMAP')
        write(folder / 'result.json', result)
        results[target] = dict(file=str(folder / 'result.json'), sha256=sha(folder / 'result.json'),
                               clusters=count, noise_models=result['noise_models'])
        del features
    write(output / 'completion.json', dict(status='validated', plan_sha256=args.plan_sha256, targets=results))
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('prepare')
    p.add_argument('--review', type=Path, required=True)
    p.add_argument('--density-source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p = commands.add_parser('run')
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--plan-sha256', required=True)
    args = parser.parse_args()
    globals()[args.command](args)
