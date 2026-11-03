# Existing complex ProteinEBM scoring

This extension scores unchanged complete complexes with native Model 6 expert
weights. It preserves each input chain, its complete sequence, native per-chain
residue indices and distinct `chain_encoding`. It never takes only the first
chain or treats two chains as one continuous protein. Contact embedding 1 retains
the upstream unknown-contact convention; this is not a binding-energy estimator.

`features.py` rejects missing/extra chains and residues, unsupported residue
numbering, missing C-alpha atoms and nonfinite coordinates. Score annotations
require exact canonical model IDs and original CIF hashes.

The run plan freezes the source, checkpoint, native configuration, original
model hashes, CPU/GPU monitoring, resource budgets and scientific settings.
Use 16 native time levels from 0 to 0.15, clean template self-conditioning,
no forward noise, no sequence masking and no inference self-conditioning.
The primary display score is t=0.10, in arbitrary learned units, lower first
within one construct. Full-length and truncated constructs have separate ranks.

CPU preparation strictly loads the matching architecture and freezes all native
features and augmentations. A counted 100-model GPU pilot checks both chains,
chain-label invariance of native relative-position features, finite per-residue
and total scores, and agreement between their sums. A CPU acceptance gate and
finished monitoring evidence precede the remaining nine 100-model GPU workers.
Each worker is a fresh bounded process; no automatic retries or CPU fallback.

The all-residue clustering config disables automatic terminal trimming. Run the
existing structure workflow separately for each construct and verify retained
residue counts against the complete two-chain input. Preserve the AFS3 model
origin: ProteinEBM is a score annotation, not the source prediction method.

Preparation and source tests do not authorize scientific execution. Follow
`docs/branch-management.md` for exact frozen-plan approval before submission.

`prepare.py` accepts the completed read-only JSONL inventory, Fleet's engine and
monitor bindings, and the saved native manifest. It creates two hash-bound plans,
ten Bash-checked batch bodies, preview-only submission commands, a canonical
source manifest and one execution plan. It never connects to remote hosts. Submission
must use the Fleet monitored front door with resolved `afterok` dependencies,
not the `.sbatch` files directly. Stage native payloads without changing originals.
Run `worker.py --help` for the explicit preparation/pilot/gate/continuation/
acceptance entry points. Verify the final acceptance job's own finished telemetry
after it exits, independently from scientific acceptance.

`export_atlas.py` reuses the repository's saved-atlas interface for completed
all-residue workflows. It verifies every original model hash and the exact
projection/membership population, preserves native CIF bytes, and exports only
relative public paths. ProteinEBM values are joined by model ID and source hash
after complete scoring acceptance. Until then, the energy option stays disabled
and values stay missing. Representatives use the highest saved AF3 ranking score
within each cluster, with their policy disclosed; no structural medoids, Bonsai,
or other uncomputed analyses are claimed. The command creates an immutable local
candidate and never publishes or runs scientific calculations.

`hdbscan.py` prepares and executes a separately approved, hash-bound all-residue
density plan using frozen native analysis source. Each construct receives a 10D
UMAP fit for seeds 42, 7 and 123, with leaf and EOM HDBSCAN extractions. Seed 42
leaf labels define the published clustering; other fits are diagnostics. Noise
remains in the complete population. Use a writable `NUMBA_CACHE_DIR` with the
approved runtime; the scientific environment itself need not be writable.

The exporter accepts `--density-results /completed/analysis --density-plan
/approved/execution-plan.json`. It verifies completion and result hashes before
adding a separate HDBSCAN view. Existing display projections and accepted
ProteinEBM values remain exact. Each point carries its original model path and
hash, allowing exact-model selection even for unassigned points. The complete
two-chain residue sidecar enables rainbow, chain and declared AF3 pLDDT coloring.

`bonsai_supplement.py prepare` freezes a separately approved two-tree supplement:
all 1,000 models per construct, every original residue pair, all nonzero centered
PCA axes without whitening, native kNN10 reconstruction and three saved layouts.
Its monitored controller enforces the quoted CPU, memory, output, free-space and
wall-time bounds. It rejects changed input/runtime hashes, unapproved plans and
existing outputs, and disables package-install fallbacks. One tree per construct
is reused across the existing Primary and HDBSCAN labels, including noise.

Pass accepted `--bonsai-results /completed/analysis --bonsai-plan /approved/plan.json`
to the exporter. Trees share the projection colors, expose exploratory native
tree groups as another color option, and load exact original models on selection.
The cluster table links each original representative CIF separately from any
ensemble exports. Compact structure controls are above the molecular canvas;
model details and downloads are below it. Renderer assets have content-versioned
URLs so returning collaborators receive the refreshed interface.
