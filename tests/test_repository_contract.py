"""Source-only project layout and pin checks; no scientific engines."""
import ast,hashlib,json,re,tomllib,unittest,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class Contract(unittest.TestCase):
    def test_single_exact_library_pin(self):
        deps=tomllib.loads((ROOT/'pyproject.toml').read_text())['project']['dependencies']
        self.assertEqual(len(deps),1)
        self.assertRegex(deps[0],r'^structure-clustering @ git\+https://github\.com/benavt/Structure_Clustering\.git@[0-9a-f]{40}$')
    def test_manifest_has_no_unhashed_artifacts(self):
        value=json.loads((ROOT/'config/publication.json').read_text());self.assertEqual(value['renderer'],'saved')
        self.assertTrue(value['files']);names=set()
        for row in value['files']:
            self.assertNotIn(row['path'],names);names.add(row['path']);self.assertRegex(row['sha256'],r'^[0-9a-f]{64}$');self.assertGreaterEqual(row['bytes'],0)
        self.assertIn('index.html',names)
        self.assertEqual(value['source_snapshot']['kind'],'github-commit-zip')
        self.assertRegex(value['source_snapshot']['commit'],r'^[0-9a-f]{40}$')
    def test_source_imports_have_exact_migration_evidence(self):
        value=json.loads((ROOT/'config/source-migration.json').read_text());self.assertFalse(value['scientific_execution'])
        for row in value['files']:
            raw=(ROOT/row['destination']).read_bytes();self.assertEqual(hashlib.sha256(raw).hexdigest(),row['project_sha256'])
            if row['destination'].endswith('.py'):ast.parse(raw)
    def test_scientific_runs_are_unselected(self):
        self.assertEqual(json.loads((ROOT/'config/run-settings.json').read_text())['new_runs'],[])
    def test_tracked_tree_is_source_only(self):
        names=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
        allowed={'.github','.gitignore','.gitmodules','AGENTS.md','LICENSES','README.md','config','external','pyproject.toml','scripts','site','tests'}
        forbidden={'.cif','.pdb','.pse','.npy','.npz','.sqlite','.sqlite3','.zip','.gz'}
        for name in filter(None,names):
            self.assertIn(name.split('/')[0],allowed)
            self.assertNotIn(Path(name).suffix.lower(),forbidden)
            path=ROOT/name
            if path.is_file():self.assertLessEqual(path.stat().st_size,5*1024**2)
    def test_new_tree_contains_no_generated_site(self):
        self.assertFalse((ROOT/'index.html').exists())
        for p in (ROOT/'scripts').rglob('*.py'):ast.parse(p.read_text())

if __name__=='__main__':unittest.main()
