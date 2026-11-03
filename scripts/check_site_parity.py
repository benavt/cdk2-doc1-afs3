"""Verify the complete original static URL/file contract before deployment."""
from pathlib import Path
import argparse,hashlib,json
from structure_clustering.publication import clustering_presentation
ROOT=Path(__file__).resolve().parents[1]

def main(site=None,source=None):
    value=json.loads((ROOT/'config/publication.json').read_text());site=Path(site or ROOT/'site/build');source=Path(source or ROOT/'local/publication-inputs')
    expected={row['path']:row for row in value['files']}
    actual={p.relative_to(site).as_posix()for p in site.rglob('*')if p.is_file()}
    if actual != set(expected)|{'.nojekyll','export-manifest.json'}:raise ValueError('Static path set changed')
    presentation={}
    if value.get('presentation',{}).get('clustering_order')=='hdbscan-first':
        saved={name:(source/name).read_bytes()for name in ['app.js','index.html']}
        for name,raw in saved.items():
            if len(raw)!=expected[name]['bytes']or hashlib.sha256(raw).hexdigest()!=expected[name]['sha256']:raise ValueError('Frozen presentation source differs: '+name)
        presentation=clustering_presentation(saved['app.js'],saved['index.html'])
    for name,row in expected.items():
        if name in presentation:row={'bytes':len(presentation[name]),'sha256':hashlib.sha256(presentation[name]).hexdigest()}
        path=site/name
        if path.stat().st_size!=row['bytes']:raise ValueError('Saved artifact size differs: '+name)
        with path.open('rb')as handle:digest=hashlib.file_digest(handle,'sha256').hexdigest()
        if digest!=row['sha256']:raise ValueError('Saved artifact SHA-256 differs: '+name)
    if (site/'.nojekyll').read_bytes()!=b'':raise ValueError('Static marker changed')
    print('Exact static paths and native bytes verified:',len(expected),'Reviewed presentation assets:',len(presentation))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--site',type=Path);parser.add_argument('--source',type=Path);args=parser.parse_args();main(args.site,args.source)
