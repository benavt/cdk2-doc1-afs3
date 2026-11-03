"""Verify the complete original static URL/file contract before deployment."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]

def main():
    value=json.loads((ROOT/'config/publication.json').read_text());site=ROOT/'site/build'
    expected={row['path']:row for row in value['files']}
    actual={p.relative_to(site).as_posix()for p in site.rglob('*')if p.is_file()}
    if actual != set(expected)|{'.nojekyll','export-manifest.json'}:raise ValueError('Static path set changed')
    for name,row in expected.items():
        path=site/name
        if path.stat().st_size!=row['bytes']:raise ValueError('Saved artifact size differs: '+name)
        with path.open('rb')as handle:digest=hashlib.file_digest(handle,'sha256').hexdigest()
        if digest!=row['sha256']:raise ValueError('Saved artifact SHA-256 differs: '+name)
    if (site/'.nojekyll').read_bytes()!=b'':raise ValueError('Static marker changed')
    print('Exact original static paths and native bytes verified:',len(expected))

if __name__=='__main__':main()
