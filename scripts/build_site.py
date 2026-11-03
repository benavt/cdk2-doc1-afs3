"""Rebuild the reviewed static snapshot; never start a scientific workflow."""
import argparse
from pathlib import Path
from structure_clustering.publication import export
from structure_clustering.snapshot import fetch_snapshot

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',type=Path,help='Use an already verified GitHub ZIP instead of downloading')
    a=p.parse_args()
    manifest=ROOT/'config/publication.json'
    source=ROOT/'local/publication-inputs'
    fetch_snapshot(manifest,source,archive=a.archive)
    record=export(manifest,source,ROOT/'site/build')
    print('Saved files passed shared blocking export privacy checks:',len(record['files']))
    return record

if __name__=='__main__':main()
