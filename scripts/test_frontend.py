"""Run project UI regressions in a temporary code-only published-site harness."""
from pathlib import Path
import argparse,shutil,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser();p.add_argument('--site',type=Path,default=ROOT/'site/build');p.add_argument('--node',default='node');a=p.parse_args()
    if not (a.site/'index.html').is_file():raise SystemExit('Build the reviewed saved site first')
    with tempfile.TemporaryDirectory()as directory:
        qa=Path(directory)
        for src in a.site.iterdir():
            if src.is_file():shutil.copy2(src,qa/src.name)
        if (a.site/'assets').exists():shutil.copytree(a.site/'assets',qa/'assets')
        shutil.copytree(ROOT/'tests/explorer',qa/'tests')
        tests=sorted(str(p)for p in (qa/'tests').iterdir()if p.suffix in {'.mjs','.cjs'})
        if tests:subprocess.run([a.node,'--test',*tests],check=True,cwd=qa)
        else:print('No project-specific JavaScript tests were present in the saved publication')

if __name__=='__main__':main()
