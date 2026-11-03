# CDK2/DOC1 project guide

Owns targets, residue selections, frozen scientific adapters and saved publication.
The library is pinned by exact reviewed commit in pyproject.toml. Read
[project contract](docs/project-contract.md) and README.md before pipeline,
repository or publication changes; preserve the public URL and saved bytes.

Use codex branches from fetched origin/main; PRs target main. Preserve dirty work,
unique commits and native outputs. Merges/tags/publication and scientific runs or
exports need their explicit scope; install/CI/merge never starts science.

Source checks: `python -m unittest discover -s tests -p test_repository_contract.py`.
Shared policy starts at pinned external/research-workflows/README.md; read only
the selected stage. Fleet owns private host/runtime/access bindings. No project
skill is required. Keep bulk data and private bindings outside source commits.
