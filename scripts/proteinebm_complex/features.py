"""Validate complete, ordered protein chains before native ProteinEBM features."""
from pathlib import Path


def ordered_complex_residues(structure, expected_chains):
    from Bio.PDB.Polypeptide import is_aa
    from Bio.SeqUtils import seq1

    models = list(structure)
    if len(models) != 1:
        raise ValueError('Exactly one coordinate model is required')
    chains = {chain.id: chain for chain in models[0]}
    expected_ids = [row['id'] for row in expected_chains]
    if len(expected_ids) != len(set(expected_ids)) or set(chains) != set(expected_ids):
        raise ValueError('Coordinate chains differ from the frozen input chains')
    residues, chain_encoding = [], []
    for encoding, row in enumerate(expected_chains):
        current = list(chains[row['id']])
        if not current or any(not is_aa(residue, standard=True) for residue in current):
            raise ValueError('Unexpected nonstandard or nonprotein residue')
        sequence = ''.join(seq1(residue.resname) for residue in current)
        if sequence != row['sequence']:
            raise ValueError('Missing, extra, or changed residues in chain ' + row['id'])
        if any('CA' not in residue or residue.id[2].strip() for residue in current):
            raise ValueError('Missing C-alpha or unsupported residue insertion')
        if [residue.id[1] for residue in current] != list(range(1, len(current) + 1)):
            raise ValueError('Expected the complete native per-chain residue numbering')
        residues.extend(current)
        chain_encoding.extend([encoding] * len(current))
    return residues, chain_encoding


def native_complex_features(path, expected_chains, converter):
    import numpy as np
    from Bio.PDB import MMCIFParser, PDBParser

    parser = MMCIFParser(QUIET=True) if Path(path).suffix.lower() in {'.cif', '.mmcif'} else PDBParser(QUIET=True)
    residues, chain_ids = ordered_complex_residues(parser.get_structure('complex', str(path)), expected_chains)
    positions, mask, amino_acids, indices = converter(residues)
    if not bool((mask[:, 1] == 1).all()) or not np.isfinite(positions.numpy()).all():
        raise ValueError('Incomplete or nonfinite native coordinates')
    return positions[:, 1], amino_acids, indices, chain_ids


def exact_score_join(models, score_rows):
    """Join by canonical ID AND original file hash; never infer positional aliases."""
    import math

    if len(models) != len(score_rows):
        raise ValueError('Incomplete energy coverage')
    lookup = {row['model_id']: row for row in score_rows}
    if len(lookup) != len(score_rows) or set(lookup) != {row['model_id'] for row in models}:
        raise ValueError('Duplicate or mismatched energy model identities')
    values = []
    for model in models:
        row = lookup[model['model_id']]
        value = float(row['energy_t010'])
        if row['sha256'] != model['sha256'] or row['method'] != model['method'] or not math.isfinite(value):
            raise ValueError('Energy source identity or numeric value differs')
        values.append(value)
    return values
