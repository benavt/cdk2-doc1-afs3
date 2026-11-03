"""Finite chain-aware Model 6 scoring; explicit execution of a frozen plan only."""
import argparse
import csv
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import checked, finished, read, require, sha, write
from features import native_complex_features

SETTINGS = dict(n_samples=16, t_min=0.0, t_max=0.15, batch_size=16,
                template_self_condition=True, inference_self_condition=False,
                ensemble_size=0, mask_sequence=False, score_norm_energy=False,
                primary_time_index=10, seed=215600, chunk_size=100)


def load(path):
    plan = read(path)
    require(plan['schema'] == 'proteinebm-complex-1000-v1' and plan['settings'] == SETTINGS,
            'Unknown or changed scoring recipe')
    rows = plan['inputs']
    require(len(rows) == len({r['model_id'] for r in rows}) == len({r['path'] for r in rows}) == 1000,
            'Expected exactly 1000 distinct original model identities')
    require(len(plan['chains']) == 2 and len({c['id'] for c in plan['chains']}) == 2,
            'Expected two explicitly identified complete chains')
    sequence = ''.join(c['sequence'] for c in plan['chains'])
    require(len(sequence) == plan['residues'] and hashlib.sha256(sequence.encode()).hexdigest() ==
            plan['sequence_sha256'], 'Frozen construct mismatch')
    for name, digest in plan['payload_sha256'].items():
        require(Path(name).name == name, 'Unsafe payload member')
        checked(Path(path).parent / name, digest)
    checked(plan['checkpoint']['path'], plan['checkpoint']['sha256'])
    checked(plan['config']['path'], plan['config']['sha256'])
    for name, digest in plan['native_files'].items():
        require(not Path(name).is_absolute() and '..' not in Path(name).parts, 'Unsafe native member')
        checked(Path(plan['native_source']) / name, digest)
    return plan


def native(plan, device):
    sys.path.insert(0, plan['native_source'])
    import numpy as np
    import torch
    import yaml
    from ml_collections import ConfigDict
    from protein_ebm.model.ebm import ProteinEBM
    from protein_ebm.model.r3_diffuser import R3Diffuser
    from protein_ebm.model.boltz_utils import center_random_augmentation
    torch.set_num_threads(1)
    config = ConfigDict(yaml.safe_load(Path(plan['config']['path']).read_text()))
    require(not config.model.diffuse_sidechain and config.model.num_contact_embeddings == 3,
            'Expected native CA expert architecture')
    if device == 'cuda':
        require(torch.cuda.is_available() and torch.cuda.device_count() == 1,
                'One CUDA GPU required; CPU inference fallback forbidden')
    model = ProteinEBM(config.model, R3Diffuser(config.diffuser)).to(device)
    checkpoint = torch.load(plan['checkpoint']['path'], map_location='cpu', weights_only=False)
    model.load_state_dict({k[len('model.'):]: v for k, v in checkpoint['state_dict'].items()
                           if k.startswith('model.')}, strict=True)
    model.eval()
    return np, torch, model, center_random_augmentation


def prepare(path, plan):
    require(not os.environ.get('CUDA_VISIBLE_DEVICES') and not os.environ.get('SLURM_JOB_GPUS'),
            'Preparation must be CPU-only')
    np, torch, model, augment = native(plan, 'cpu')
    del model
    from protein_ebm.data.protein_utils import residues_to_features, restypes
    atoms, aa, idx, chains = [], [], [], []
    for row in plan['inputs']:
        checked(row['path'], row['sha256'])
        checked(row['summary_path'], row['summary_sha256'])
        positions, amino_acids, indices, chain_ids = native_complex_features(
            row['path'], plan['chains'], residues_to_features)
        sequence = ''.join(restypes[int(a)] for a in amino_acids)
        require(hashlib.sha256(sequence.encode()).hexdigest() == plan['sequence_sha256'],
                'Native residue identities differ')
        atoms.append(positions); aa.append(amino_acids); idx.append(indices)
        chains.append(torch.tensor(chain_ids, dtype=torch.long))
    atoms, aa, idx, chains = map(torch.stack, (atoms, aa, idx, chains))
    torch.manual_seed(SETTINGS['seed']); np.random.seed(SETTINGS['seed'])
    times = torch.linspace(0.0, 0.15, 16)
    coords = torch.stack([augment(atoms, torch.ones((1000, plan['residues']))) for _ in times])
    arrays = dict(coords=coords.numpy(), aatype=aa.numpy(), idx=idx.numpy(),
                  chain_ids=chains.numpy(), times=times.numpy())
    cache = Path(plan['run_root']) / '02_design/features.npz'
    with cache.open('xb') as stream:
        np.savez(stream, **arrays)
    with np.load(cache, allow_pickle=False) as actual:
        require(all(np.array_equal(v, actual[k]) for k, v in arrays.items()), 'Lossy cache roundtrip')
    write(cache.parent / 'ready.json', dict(status='validated', CPU_only=True,
          plan_sha256=sha(path), feature_sha256=sha(cache), both_chains_complete=True,
          models=1000, residues=plan['residues'], native_cpu_strict_load=True))


def ready(path, plan):
    proof = finished(plan['attempts']['prepare'], plan['monitor'])
    marker = read(Path(plan['run_root']) / '02_design/ready.json')
    require(marker['status'] == 'validated' and marker['CPU_only'] and marker['both_chains_complete']
            and marker['native_cpu_strict_load'] and marker['plan_sha256'] == sha(path), 'CPU cache not ready')
    cache = Path(plan['run_root']) / '02_design/features.npz'
    checked(cache, marker['feature_sha256'])
    return cache, proof


def gpu(path, plan, chunk):
    require(type(chunk) is int and 0 <= chunk < 10, 'Invalid bounded chunk')
    cache_path, proof = ready(path, plan)
    if chunk:
        checked_gate(path, plan)
    np, torch, model, _ = native(plan, 'cuda')
    torch.cuda.manual_seed_all(SETTINGS['seed'])
    start = time.monotonic()
    begin, end = chunk * 100, (chunk + 1) * 100
    with np.load(cache_path, allow_pickle=False) as archive:
        cache = {k: archive[k] for k in archive.files}
    aa = torch.from_numpy(cache['aatype'][begin:end]).cuda()
    idx = torch.from_numpy(cache['idx'][begin:end]).cuda()
    ce = torch.from_numpy(cache['chain_ids'][begin:end]).cuda()
    require(set(ce[0].tolist()) == {0, 1}, 'Chain identity lost in cache')
    with torch.no_grad():
        require(torch.equal(model.rel_pos(idx[:1], ce[:1]), model.rel_pos(idx[:1], 1 - ce[:1])),
                'Native pair features changed under chain relabeling')
        energies, residues = [], []
        for ti, t in enumerate(cache['times']):
            level, per_residue = [], []
            for offset in range(0, 100, SETTINGS['batch_size']):
                stop = min(offset + SETTINGS['batch_size'], 100)
                coords = torch.from_numpy(cache['coords'][ti, begin+offset:begin+stop]).cuda()
                a, indices, chain_ids = aa[offset:stop], idx[offset:stop], ce[offset:stop]
                mask = torch.ones(a.shape, device='cuda')
                result = model.compute_energy(dict(aatype=a, residue_idx=indices, mask=mask,
                    chain_encoding=chain_ids, external_contacts=torch.ones_like(a),
                    selfcond_coords=coords, r_noisy=coords, atom_mask=mask,
                    t=torch.full((stop-offset,), float(t), device='cuda')))
                values = result['energy'].cpu().numpy()
                partial = result['per_residue_energy'].cpu().numpy()
                require(np.isfinite(values).all() and np.isfinite(partial).all()
                        and np.allclose(partial.sum(-1), values, rtol=2e-6, atol=2e-5),
                        'Incomplete, nonfinite, or inconsistent native energies')
                level.append(values); per_residue.append(partial)
                require(torch.cuda.max_memory_allocated() < 56 * 2**30, 'GPU memory budget exceeded')
                del coords, result
            energies.append(np.concatenate(level)); residues.append(np.concatenate(per_residue))
    output = Path(plan['run_root']) / '02_design' / f'chunk-{chunk:02d}.npz'
    with output.open('xb') as stream:
        np.savez(stream, energy=np.stack(energies), per_residue_energy=np.stack(residues), times=cache['times'])
    write(output.with_suffix('.json'), dict(status='validated', plan_sha256=sha(path),
          chunk=chunk, models=100, energies=1600, output_sha256=sha(output),
          chain_relabel_pair_features_exact=True, CPU_resource_evidence=proof,
          seconds=time.monotonic()-start, peak_gpu_bytes=torch.cuda.max_memory_allocated()))


def checked_gate(path, plan):
    finished(plan['attempts']['gate'], plan['monitor'])
    gate = read(Path(plan['run_root']) / '03_filtering/pilot-gate.json')
    require(gate['status'] == 'validated' and gate['plan_sha256'] == sha(path), 'Pilot gate not accepted')
    checked(Path(plan['run_root']) / '02_design/chunk-00.npz', gate['pilot_sha256'])


def gate(path, plan):
    evidence = finished(plan['attempts']['pilot'], plan['monitor'], gpu=True)
    result = read(Path(plan['run_root']) / '02_design/chunk-00.json')
    require(result['status'] == 'validated' and result['models'] == 100 and
            result['plan_sha256'] == sha(path) and result['chain_relabel_pair_features_exact'],
            'Counted two-chain pilot failed')
    output = Path(plan['run_root']) / '02_design/chunk-00.npz'
    checked(output, result['output_sha256'])
    write(Path(plan['run_root']) / '03_filtering/pilot-gate.json', dict(status='validated',
          plan_sha256=sha(path), pilot_sha256=sha(output), pilot_resource_evidence=evidence))


def production(path, plan):
    checked_gate(path, plan)
    for chunk in range(1, 10):
        # One fresh finite native child; whole-job telemetry includes it.
        subprocess.run([plan['python'], '-I', str(Path(__file__).resolve()), 'gpu',
                        '--plan', str(path), '--plan-sha256', plan['_approved_sha256'],
                        '--chunk', str(chunk)], check=True, timeout=600)


def accept(path, plan):
    evidence = {phase: finished(plan['attempts'][phase], plan['monitor'], gpu=phase in {'pilot', 'production'})
                for phase in ['prepare', 'pilot', 'gate', 'production']}
    import numpy as np
    root = Path(plan['run_root'])
    chunks, chunk_hashes = [], []
    for index in range(10):
        file = root / '02_design' / f'chunk-{index:02d}.npz'
        result = read(file.with_suffix('.json'))
        checked(file, result['output_sha256'])
        require(result['status'] == 'validated' and result['plan_sha256'] == sha(path)
                and result['chunk'] == index, 'Wrong scoring chunk')
        with np.load(file, allow_pickle=False) as data:
            energy, partial = data['energy'], data['per_residue_energy']
            require(energy.shape == (16, 100) and partial.shape == (16, 100, plan['residues'])
                    and np.isfinite(energy).all() and np.isfinite(partial).all()
                    and np.allclose(partial.sum(-1), energy, rtol=2e-6, atol=2e-5)
                    and np.allclose(data['times'], np.linspace(0, .15, 16), atol=2e-8, rtol=0),
                    'Invalid complete energy grid')
            chunks.append(energy.copy())
        chunk_hashes.append(sha(file))
    energies = np.concatenate(chunks, axis=1)
    values = energies[10]
    ranks = {value: 1 + int((values < value).sum()) for value in values}
    rows = []
    for i, model in enumerate(plan['inputs']):
        checked(model['path'], model['sha256'])
        rows.append(dict(method=model['method'], model_id=model['model_id'], path=model['path'],
                         sha256=model['sha256'], energy_t010=float(values[i]), rank_t010=ranks[values[i]],
                         mean_energy=float(energies[:, i].mean()),
                         **{f'energy_t{j:02d}': float(energies[j, i]) for j in range(16)}))
    output = root / '04_analysis/energy-rankings.csv'
    with output.open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    write(root / '04_analysis/acceptance.json', dict(status='validated', target=plan['target'],
          models=1000, energies=16000, residues=plan['residues'], sequence_sha256=plan['sequence_sha256'],
          plan_sha256=sha(path), source_manifest_sha256=plan['source_manifest_sha256'], csv_sha256=sha(output),
          resource_evidence=evidence, chunk_sha256=chunk_hashes,
          scope='Complete two-chain construct; arbitrary learned units, lower within construct'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['prepare', 'pilot', 'gpu', 'gate', 'production', 'accept'])
    parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--chunk', type=int)
    args = parser.parse_args()
    checked(args.plan, args.plan_sha256)
    plan = load(args.plan)
    plan['_approved_sha256'] = args.plan_sha256
    if args.phase in {'pilot', 'gpu'}:
        gpu(args.plan, plan, 0 if args.phase == 'pilot' else args.chunk)
    else:
        globals()[args.phase](args.plan, plan)
    checked(args.plan, args.plan_sha256)


if __name__ == '__main__':
    main()
