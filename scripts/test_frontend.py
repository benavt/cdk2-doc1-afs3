"""Run project UI regressions in a temporary code-only published-site harness."""
from pathlib import Path
import argparse,gzip,json,shutil,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser();p.add_argument('--site',type=Path,default=ROOT/'site/build');p.add_argument('--node',default='node');a=p.parse_args()
    if not (a.site/'index.html').is_file():raise SystemExit('Build the reviewed saved site first')
    test_source=ROOT/'tests/explorer'
    if not test_source.is_dir():
        print('No project-specific JavaScript tests were present in the saved publication');return
    with tempfile.TemporaryDirectory()as directory:
        qa=Path(directory)
        for src in a.site.iterdir():
            if src.is_file():shutil.copy2(src,qa/src.name)
        if (a.site/'assets').exists():shutil.copytree(a.site/'assets',qa/'assets')
        # The retained target-context test reads only each target's saved analysis JSON.
        context=next((p for p in (a.site/'target-context.json',a.site/'target-context.json.gz')if p.is_file()),None)
        if context:
            raw=context.read_bytes();metadata=json.loads(gzip.decompress(raw)if context.suffix=='.gz'else raw)
            for target in metadata['targets']:
                if Path(target).name!=target or target in {'.','..'}:raise ValueError('Unsafe target path')
                src=a.site/target/'primary.json.gz'
                if src.is_file():
                    (qa/target).mkdir();shutil.copy2(src,qa/target/src.name)
        shutil.copytree(test_source,qa/'tests')
        tests=sorted(str(p)for p in (qa/'tests').iterdir()if p.suffix in {'.mjs','.cjs'})
        if tests:subprocess.run([a.node,'--test',*tests],check=True,cwd=qa)
        else:print('No project-specific JavaScript tests were present in the saved publication')

if __name__=='__main__':main()
