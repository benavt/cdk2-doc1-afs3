# CDK2/DOC1 AFSample3 and ProteinEBM analysis

This project owns its targets, residue ranges, run configuration and pipeline
adapters. Start `codex/<task>` branches from freshly fetched `origin/main`; PRs
target main. Preserve unique work and use separate worktrees for concurrent edits.
Install the reusable library from the exact full commit in pyproject.toml.
Structure_Clustering is a pip dependency, not a submodule or adjacent source clone.

Source checks: `python -m unittest discover -s tests -p test_repository_contract.py`.
Publication: `python scripts/build_site.py`; it consumes only the frozen saved
snapshot in config/publication.json. Generated output is site/build, never source.
Use `structure-clustering check-privacy --tracked` and check the generated site.
The checker implementation is shared in the installed library.

Do not commit models, matrices, ensembles, native run outputs, credentials or
private runtime/machine bindings. Keep manifests with exact sizes and SHA-256.
Do not run scientific adapters, resume historical plans or regenerate results
from installation, CI setup, a merge, or this migration. The copied controllers
retain their scientific settings; new execution needs a separately approved
project-scoped plan and native validation. Preserve existing frozen paths/jobs.

Public URL: https://benavt.github.io/cdk2-doc1-afs3/ . Preserve its relative artifact URLs
and saved scientific bytes. Hosting-source changes and merges need approval of
the reviewed change. Keep the old deployment until a reviewed cutover. New tags
and release/archival publication need their applicable explicit authorization.
Fleet owns private host/runtime/access bindings. Shared workflow guidance belongs
in research-workflows; keep project-specific adapters here.

Shared policy starts at external/research-workflows/README.md and its selected
contract/stage. Its separate pin retains the producer workflow contract; native
scientific settings are not changed by this source adoption.
