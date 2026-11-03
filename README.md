# CDK2/DOC1 AFSample3 and ProteinEBM analysis

This repository owns project configuration and pipeline adapters. The library,
CLI, reusable algorithms and renderer remain in the exactly pinned
Structure_Clustering dependency. The published URL remains
https://benavt.github.io/cdk2-doc1-afs3/ .

`config/` contains targets, saved ranges, run-selection state, migration evidence
and the complete publication SHA-256 manifest. `scripts/` contains the project
controllers and saved-site front door. `site/build/` is generated and ignored.
No model population or analysis output is committed in the proposed source tree.

Run source checks with `python -m unittest discover -s tests -p test_repository_contract.py`.
With the exact private library installed, `python scripts/build_site.py` fetches
one pinned public snapshot, verifies both its ZIP hash and every selected member,
then runs `structure-clustering export` and the shared blocking privacy checker.
No fitting, scoring, sampling or native structure/session export occurs.

The migration preserves the existing presentation and native bytes using
`renderer: saved`. Its source is publication commit `d672ba45d8a7723ac07041f41410b1150a2b33e6`. The old Git history
and independently retained scientific outputs remain intact. This is an explicit
historical snapshot transport while durable release/archival assets are prepared;
no release tag, history rewrite or local scientific retirement is authorized by
the source migration. Future transport changes must preserve native member hashes.

Before adopting the canonical renderer for a later dependency upgrade, complete
UI/feature parity against the project's currently approved presentation. A library
pin bump never silently changes scientific results or an approved saved view.

The reviewed `presentation.clustering_order: hdbscan-first` option opens HDBSCAN
and keeps UMAP KNN as the alternative and unavailable-result fallback. Explicit
saved-view links retain their selection. The shared library updates only the
clustering menu/routing functions and app cache key; all scientific files and
project-specific point-model inspection remain unchanged. Site parity checks
derive both presentation files from the verified frozen originals.

The copied scientific controllers retain their numeric settings and frozen source
anchors. They are source-migration candidates, not approval to execute or resume
historical batches. New project-scoped source/runtime inventories and native
validation are required before a separately approved new scientific run. Existing
active jobs and their historical paths are not rebound by this proposal.

Source CI and manual publication need `STRUCTURE_CLUSTERING_READ_TOKEN`, limited
to read-only library access, supplied through this repository's GitHub secret store.
Never place credentials in pyproject, source, artifact URLs or chat. Source CI must
pass before merge. Static publication is manual and bound to the exact reviewed
manifest hash. Its uploaded artifact contains site/build at the Pages root, so
relative download URLs retain their existing paths.

Current hosting still uses legacy `main:/`. Do not merge the root-asset removal
until the reviewed cutover coordinates artifact deployment with the Pages build
source switch. Restore from the recorded immutable snapshot if a cutover fails;
keep the previous deployment available until byte/link verification passes.

The previous public privacy-check implementation is replaced by a thin shared-CLI
entry point. Frontend regression tests stay in tests/explorer and run against a
temporary code-only harness via `python scripts/test_frontend.py` after a build.
Original scientific datasets, native coordinate exports and their canonical host
locations are unchanged. Imported adapters retain the source MIT notice in LICENSES/.

For a new source-only checkout, use Git partial clone (`git clone --filter=blob:none`)
to avoid downloading historical publication blobs. Git history is preserved.
The separate research-workflows policy pin retains the producer contract.

## Workflow library contract

The exact dependency pin includes the shared immutable-intake, run-local metrics,
verified recovery and report-pagination changes. Merge this pin update only after
the library PR is reviewed and its commit remains reachable. The previous pin is
retained in Git for rollback. This source update selects no scientific run and
does not regenerate the saved site or change its manifest, URLs or bytes.

New generic analyses use `structure-clustering inspect-inputs` and
`structure-clustering analyze --plan` before a separately approved run. They expand
all conformers, preserve native chain IDs, require explicit chain correspondence
when needed, and leave expanded conformers unscored without an explicit score map.
Metrics are fresh and run-local unless an explicit database is supplied; that
database's stored label rules are retained unless overridden. New run recovery
requires identical inputs, settings, library revision and runtime. The complete molecular report is the default; `--analysis-only` selects the
reduced deliverable. All clusters receive additional report pages when needed.

The project-owned ProteinEBM controllers retain their scientific settings and
frozen paths. Their historical manifests do not acquire the generic recovery
contract through a dependency upgrade. Source/import and frozen-manifest checks
are compatibility evidence, not native scientific validation of a new run.
