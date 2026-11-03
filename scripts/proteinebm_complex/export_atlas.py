"""Export accepted workflow projections with the repository's saved-atlas UI.

Reads existing results only. Missing energies stay unavailable; coordinate files
retain their original bytes. No clustering, energy inference or publication runs.
"""
import argparse
import csv
from copy import deepcopy
import colorsys
import hashlib
import html
import json
import math
from pathlib import Path
import re
import shutil
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))
from common import checked, read, sha, write
from features import exact_score_join
from src.analysis.atlas_presentation import ASSETS, validate_views
from importlib.resources import files
TEMPLATES = Path(str(files("src.app").joinpath("templates")))


def continuous(key, name, values):
    finite = [v for v in values if v is not None and math.isfinite(v)]
    return dict(key=key, name=name, short_name=name, type='continuous', values=values,
                colorscale='Viridis', range=[min(finite), max(finite)] if finite else [0, 1],
                unavailable=not finite)


def accepted_energies(folder, plan, names):
    if folder is None:
        return [None] * len(names)
    acceptance = read(folder / 'acceptance.json')
    table = folder / 'energy-rankings.csv'
    checked(table, acceptance['csv_sha256'])
    if not (acceptance['status'] == 'validated' and acceptance['target'] == plan['target']
            and acceptance['models'] == 1000 and acceptance['energies'] == 16000
            and acceptance['sequence_sha256'] == plan['sequence_sha256']
            and acceptance['source_manifest_sha256'] == plan['source_manifest_sha256']):
        raise ValueError('Energy acceptance differs from this exact construct and input cohort')
    with table.open() as stream:
        rows = list(csv.DictReader(stream))
    by_name = {row['model_id']: row for row in plan['inputs']}
    return exact_score_join([by_name[name] for name in names], rows)


def presentation_html(title, *, include_bonsai=False):
    text = (TEMPLATES / 'ais_explorer.html').read_text()
    text = text.replace('AIS · saved clustering comparison', html.escape(title))
    text = text.replace('AIS / CASP17', html.escape(title))
    text = text.replace('CASP17 AIS ·', html.escape(title) + ' ·')
    text = text.replace('Compare saved clustering protocols on the same structural maps, inspect representative ensembles and review their structural similarity. Changing a view or filter reuses saved results.',
                        'Compare PCA, UMAP and t-SNE maps of the complete two-chain constructs. Click a plotted point to load that exact original model. Color the maps by AFS3 scores or ProteinEBM energy, and the structure by rainbow, pLDDT or chain.')
    text = text.replace('Select a point to view its cluster’s medoid or ensemble.',
                        'Select a plotted point to inspect its exact original model. Cluster menus select representatives.')
    text = text.replace('<th>Medoid method</th>', '<th>Model origin</th>')
    if not include_bonsai:
        text = text.replace('Show all four views', 'Show all three projections')
        text = text.replace('All four views are shown below', 'All three projections are shown below')
        text = text.replace('Legend clicks filter all four views.', 'Legend clicks filter all projections.')
        text = text.replace('</head>', '<style>#bonsaiPanel,#bonsaiTab,[data-view="bonsai"]{display:none!important}</style></head>')
    else:
        text = text.replace('Compare PCA, UMAP and t-SNE maps of the complete two-chain constructs.',
                            'Compare PCA, UMAP, t-SNE and Bonsai views of the complete two-chain constructs.')
        text = text.replace('The Bonsai tree shows the saved models listed beneath the plot.',
                            'The Bonsai tree contains all 1,000 original models of the selected construct, including HDBSCAN unassigned models. The same native tree is reused across the Primary and HDBSCAN views.')
        text = text.replace('Select a point to show its cluster’s saved representative in the 3D viewer.',
                            'Select a Bonsai point to show that exact original model in the 3D viewer. Cluster-table rows select representatives and provide their original CIF downloads.')
    text = text.replace('Median distances summarize the sampled structures. Distance variance highlights flexible residue pairs; marked terminal regions were excluded from clustering.',
                        'Saved Cα distance summaries describe the complete two-chain construct. All residues are included; no terminal regions were excluded from clustering.')
    start = text.index('<p>Saved cohorts include models')
    end = text.index('<p id="mask">', start)
    methods = ('<p>Each target contains all 1,000 archived AFSample3 samples: 200 seeds × 5 samples. '
               'Constructs are analyzed separately, using every Cα residue of both chains. No terminal trimming is applied.</p>'
               '<p id="clusterMethod"></p>'
               '<p>ProteinEBM Model 6 expert energies score the complete two-chain construct at 16 conditioning levels. '
               'Color by exposes t=0.10 after all 1,000 scores for that construct are accepted. '
               'Values are learned arbitrary units, with lower values ranked first within one construct. '
               'They are not calibrated binding energies and are not comparable across constructs.</p>'
               '<p>Cluster representatives are the models with the highest saved AF3 ranking score within each cluster; '
               'ties use canonical model identity. They are not claimed to be structural medoids. '
               'Cluster populations describe generated samples, not equilibrium probabilities.</p>'
               '<p>Sources: <a href="https://github.com/wallnerlab/afsample3">AFSample3</a> · '
               '<a href="https://github.com/jproney/ProteinEBM">ProteinEBM</a>. '
               'Original coordinates and a complete membership/score CSV are available for each construct.</p>')
    if include_bonsai:
        methods += ('<p><a href="https://github.com/dhdegroot/Bonsai-data-representation">Bonsai</a> '
                    '(CC BY-NC 4.0) uses all 1,000 models of each construct and the same complete Cα-distance features. '
                    'All nonzero centered PCA axes are retained without whitening or variance scaling; native reconstruction uses kNN=10. '
                    'One tree per construct supplies three native layouts and is reused across the saved clustering views. '
                    'The optional Bonsai tree-group colors are exploratory native edge cuts chosen by in-sample tree-path silhouette; '
                    'they do not replace the Primary or HDBSCAN memberships.</p>')
    return text[:start] + methods + text[end:]


def bonsai_view(data, payload, workflow):
    """Attach one accepted full-cohort tree without altering saved cluster labels."""
    rows = payload['models']; provenance = payload['provenance']
    by_name = {row['model']: row for row in rows}
    if (len(rows) != len(by_name) or set(by_name) != set(data['models'])
            or provenance['source_manifest_sha256'] != data['provenance']['input_manifest_sha256']
            or provenance['sequence_sha256'] != data['provenance']['sequence_sha256']
            or provenance['residues'] != data['residues']
            or provenance['retained_reference_positions'] != workflow['terminal_detection']['retained_reference_positions']
            or provenance['pair_mask_sha256'] != workflow['terminal_detection']['pair_mask_sha256']):
        raise ValueError('Bonsai differs from the exact complete construct and residue geometry')
    settings = provenance['settings']
    if settings['max_components'] is not None or settings['rescale_by_var'] is not False or settings['use_knn'] != 10:
        raise ValueError('Bonsai geometry differs from the approved unscaled full-rank settings')
    if {layout['key'] for layout in payload['layouts']} != {'ly_eq_angle','ly_eq_daylight','ly_dendrogram_ladderized'}:
        raise ValueError('Missing native Bonsai layouts')
    labels = [by_name[name]['bonsai_group'] for name in data['models']]
    groups = sorted(set(labels))
    if len(groups) != payload['group_count']:
        raise ValueError('Bonsai group identities differ')
    palette = {label: '#' + ''.join(f'{round(v*255):02x}' for v in colorsys.hsv_to_rgb(
              (i*.618033988749895) % 1, .68, .75)) for i,label in enumerate(groups)}
    return dict(key='bonsai_groups', name='Bonsai tree groups · exploratory', short_name='Bonsai tree groups',
                type='categorical', values=labels, colors=palette)


def density_view(base, result, summaries):
    """Bind completed density labels to the exact unchanged display population."""
    if (result['target'] != base['target'] or result['models'] != base['models']
            or len(result['labels']) != len(base['models'])
            or result['source_manifest_sha256'] != base['provenance']['input_manifest_sha256']
            or result['sequence_sha256'] != base['provenance']['sequence_sha256']
            or result['residues'] != base['residues']):
        raise ValueError('Density results differ from the exact saved all-residue cohort')
    labels = result['labels']
    if any(not re.fullmatch(r'H\.[1-9][0-9]*|H\.unassigned', x) for x in labels):
        raise ValueError('Invalid density label or noise identity')
    groups = sorted({label for label in labels if not label.endswith('.unassigned')},
                    key=lambda label: int(label.split('.')[1]))
    if len(groups) != result['clusters'] or sum(x.endswith('.unassigned') for x in labels) != result['noise_models']:
        raise ValueError('Density population counts differ')
    colors = {label: '#' + ''.join(f'{round(v*255):02x}' for v in colorsys.hsv_to_rgb(
              (i*.618033988749895) % 1, .68, .75)) for i, label in enumerate(groups)}
    colors['H.unassigned'] = '#808080'
    data = deepcopy(base)
    data.update(view_id='density', view_title=base['target'] + ' · HDBSCAN · all residues',
                clusters=list(labels), representatives=[], membership_file=base['target'] + '/hdbscan-memberships-and-scores.csv',
                clustering_method_note='Whole-cohort raw all-residue Cα distances → 10D UMAP (30 neighbors, min_dist=0) → leaf HDBSCAN (min_cluster_size=15, min_samples=11). Seed 42 defines labels; seeds 7/123 and EOM are diagnostics. Unassigned models remain visible. PCA/UMAP/t-SNE display coordinates and all ProteinEBM values are unchanged.')
    next(s for s in data['schemes'] if s['key'] == 'clusters').update(values=list(labels), colors=colors)
    for label in groups:
        indices = [i for i, value in enumerate(labels) if value == label]
        index = min(indices, key=lambda i: (-float(summaries[base['models'][i]].get('ranking_score', -math.inf)), base['models'][i]))
        data['representatives'].append(dict(cluster=label, count=len(indices), model=base['models'][index],
            method=base['methods'][index], color=colors[label], file=base['model_files'][index],
            format='cif', sha256=base['model_sha256'][index]))
    data['provenance'].update(density_plan_sha256=result['plan_sha256'],
                              density_feature_proof=result['feature_proof'],
                              density_diagnostics=result['diagnostics']['seed_agreement'])
    return data


def export(args):
    import numpy as np

    review = args.review.absolute()
    execution = read(review / 'execution-plan.json')
    completed = read(review / 'clustering-complete.json')
    intake = read(review / 'collection-receipt.json')
    output = args.output.absolute()
    if output.exists():
        raise ValueError('Use a new immutable export candidate')
    output.mkdir(parents=True)
    for name, template in ASSETS.items():
        destination = output / name; destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(TEMPLATES / template, destination)
    for name in ('plotly.min.js', '3Dmol-min.js'):
        shutil.copyfile(args.vendor_assets / name, output / 'assets' / name)
    (output / 'index.html').write_text(presentation_html(args.title, include_bonsai=bool(args.bonsai_results)))
    (output / '.nojekyll').write_text('')
    atlas, context, status, residue_catalog = [], {}, {}, {}
    density = read(args.density_results / 'completion.json') if args.density_results else None
    if density and density['status'] != 'validated':
        raise ValueError('HDBSCAN analysis is not accepted')
    density_plan = None
    if density:
        path = args.density_plan or args.density_results.parent / 'execution-plan.json'
        checked(path, density['plan_sha256'])
        density_plan = read(path)
    bonsai = read(args.bonsai_results/'completion.json') if args.bonsai_results else None
    if bonsai:
        if bonsai['status'] != 'validated':
            raise ValueError('Bonsai analysis is not accepted')
        checked(args.bonsai_plan, bonsai['plan_sha256'])
    for target, target_info in execution['targets'].items():
        plan = read(review / 'payload' / (target + '.json'))
        workflow = read(completed[target]['manifest'])
        checked(completed[target]['manifest'], completed[target]['manifest_sha256'])
        expected = {row['model_id']: row for row in plan['inputs']}
        projections, names = {}, None
        for method in ('pca', 'umap', 'tsne'):
            with np.load(workflow['clustering'][method]['embeddings'], allow_pickle=False) as data:
                current = [str(value) for value in data['filenames']]
                if len(current) != 1000 or set(current) != set(expected) or names is not None and names != current:
                    raise ValueError('Projection model identities/order differ')
                names = current
                projections[method] = dict(xy=data['embeddings'].tolist(), axes=[method.upper() + ' 1', method.upper() + ' 2'])
                if method == 'pca':
                    ratios = workflow['clustering'][method].get('explained_variance_ratio')
                    if ratios:
                        projections[method].update(explained_variance_ratio=ratios,
                            axes=[f'PC {i+1} ({100*v:.1f}% variance)' for i, v in enumerate(ratios[:2])])
        with Path(workflow['knn_clustering']['labels_csv']).open() as stream:
            labels = {row['model']: row for row in csv.DictReader(stream)}
        if set(labels) != set(names) or len(workflow['terminal_detection']['retained_reference_positions']) != plan['residues']:
            raise ValueError('Clustering identities or full residue mask differ')
        raw = Path(intake['targets'][target])
        folder = output / target; (folder / 'models').mkdir(parents=True)
        summary = {}
        for name in names:
            source = raw / (name + '.cif'); checked(source, expected[name]['sha256'])
            body = source.read_bytes()
            if re.search(rb'(?i)/(?:home|users|scratch)/|tail[a-z0-9]+\.ts\.net|gh[pousr]_[A-Za-z0-9]{25,}', body):
                raise ValueError('Private data found in a coordinate candidate')
            (folder / 'models' / source.name).write_bytes(body)
            summary[name] = read(raw / (name + '_summary_confidences.json'))
        scores_folder = args.scores / target if args.scores else None
        energies = accepted_energies(scores_folder, plan, names)
        ready = all(value is not None for value in energies)
        cluster_values = [labels[name]['cluster_label'] for name in names]
        colors = {labels[name]['cluster_label']: labels[name]['color'] for name in names}
        schemes = [dict(key='clusters', name='Clusters', type='categorical', values=cluster_values, colors=colors)]
        for key, title in [('iptm', 'AF3 ipTM'), ('ptm', 'AF3 pTM'), ('ranking_score', 'AF3 ranking score')]:
            values = [float(summary[name][key]) if summary[name].get(key) is not None else None for name in names]
            schemes.append(continuous(key, title, values))
        energy = continuous('protein_ebm_energy_t10', 'ProteinEBM energy · t=0.10', energies)
        energy.update(time_index=10, time_value=.1, model_version=6, units='arbitrary', lower_is_better=True,
                      primary=True, metric_scope_count=plan['residues'],
                      metric_note='Full-construct learned energy in arbitrary units; lower within one construct.')
        schemes.append(energy)
        representatives = []
        for label in sorted(colors):
            members = [name for name in names if labels[name]['cluster_label'] == label]
            chosen = min(members, key=lambda name: (-float(summary[name].get('ranking_score', -math.inf)), name))
            representatives.append(dict(cluster=label, count=len(members), model=chosen, method='AFSample3',
                color=colors[label], file=f'{target}/models/{chosen}.cif', format='cif', sha256=expected[chosen]['sha256']))
        table = folder / 'memberships-and-scores.csv'
        with table.open('x', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['model', 'seed', 'sample', 'cluster', 'AF3_ipTM', 'AF3_pTM', 'AF3_ranking_score', 'ProteinEBM_energy_t010', 'model_file'])
            for i, name in enumerate(names):
                writer.writerow([name, expected[name]['seed'], expected[name]['sample'], cluster_values[i],
                    *[summary[name].get(key) for key in ['iptm', 'ptm', 'ranking_score']], energies[i], f'models/{name}.cif'])
        data = dict(target=target, view_id='whole', view_title=target + ' · all residues', models=names,
            residues=plan['residues'], methods=['AFSample3']*1000, clusters=cluster_values,
            projections=projections, schemes=schemes, representatives=representatives,
            views=[dict(id='whole', name='Validated UMAP clusters', data=f'{target}/primary.json')],
            membership_file=f'{target}/{table.name}', heatmaps=[],
            representative_kind='highest AF3-ranking-score representative',
            representative_policy='Highest saved AF3 ranking score in each cluster; ties use canonical model identity. Original full two-chain coordinates; no structural-medoid claim.',
            mask_note=f'All {plan["residues"]} residues from both chains; no trimming or exclusions.',
            clustering_method_note='PCA, UMAP and t-SNE use the same all-residue Cα-distance features. Default UMAP component clustering preserves disconnected components; subdivisions require structural-feature silhouette ≥0.15 and repeat-seed ARI ≥0.80. Identical cluster memberships color every projection.',
            provenance=dict(source_commit=execution['source_commit'], sequence_sha256=plan['sequence_sha256'],
                input_manifest_sha256=plan['source_manifest_sha256'], archived_run_date='2026-08-07',
                sampling='AFSample3; 200 seeds × 5 samples; 40% MSA masking',
                all_residues=True, energy_status='accepted' if ready else 'queued; values unavailable',
                energy_checkpoint_sha256=plan['checkpoint']['sha256'],
                energy_units='learned arbitrary units; lower within construct; not calibrated binding energy'))
        data.update(model_files=[f'{target}/models/{name}.cif' for name in names],
                    model_sha256=[expected[name]['sha256'] for name in names],
                    structure_confidence=dict(kind='plddt', source='AF3 mmCIF atom_site.B_iso_or_equiv'))
        for image in workflow.get('visualize_distogram', {}).get('images', []):
            source = Path(image)
            destination = folder / 'figures' / source.name
            destination.parent.mkdir(exist_ok=True)
            shutil.copyfile(source, destination)
            data['heatmaps'].append(dict(name=source.stem.replace('_', ' ').capitalize(),
                                         file=f'{target}/figures/{source.name}'))
        scope = dict(chain=','.join(c['id'] for c in plan['chains']),
            chains=[dict(chain=c['id'], expected_ca_count=len(c['sequence'])) for c in plan['chains']],
            sequence_sha256=plan['sequence_sha256'], expected_ca_count=plan['residues'],
            canonical_positions=list(range(1, plan['residues']+1)), analysis_uses_full_construct=True,
            regions_verified=False, reference_ranges='all residues of chains A and B',
            note='Ordered complete input chains; the same original coordinates are used in every view.')
        residue_catalog[target] = {'views': {'whole': scope}}
        if bonsai:
            entry = bonsai['targets'][target]; checked(entry['file'], entry['sha256'])
            tree = read(entry['file'])
            if tree['provenance']['plan_sha256'] != bonsai['plan_sha256']:
                raise ValueError('Bonsai result belongs to another execution plan')
            data['schemes'].append(bonsai_view(data, tree, workflow))
            destination = folder/'bonsai.json'; shutil.copyfile(entry['file'], destination)
            data['bonsai'] = dict(file=f'{target}/bonsai.json', sha256=entry['sha256'], selected_models=1000)
            data['provenance'].update(bonsai_plan_sha256=bonsai['plan_sha256'],
                bonsai_scope='All 1000 original models and every residue; native tree shared across saved clustering views.')
        if density:
            entry = density['targets'][target]
            checked(entry['file'], entry['sha256'])
            result = read(entry['file'])
            if result['plan_sha256'] != density['plan_sha256']:
                raise ValueError('HDBSCAN result belongs to another execution plan')
            data['views'].append(dict(id='density', name='10D UMAP / HDBSCAN', data=f'{target}/density.json'))
            dense = density_view(data, result, summary)
            dense['provenance']['density_source_commit'] = density_plan['source_commit']
            write(folder / 'density.json', dense)
            residue_catalog[target]['views']['density'] = deepcopy(scope)
            with (folder / 'hdbscan-memberships-and-scores.csv').open('x', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow(['model', 'cluster', 'ProteinEBM_energy_t010', 'model_file'])
                writer.writerows((name, dense['clusters'][i], energies[i], f'models/{name}.cif') for i, name in enumerate(names))
        write(folder / 'primary.json', data)
        atlas.append(dict(id=target, data=f'{target}/primary.json'))
        context[target] = dict(title='CDK2–DOC1 AFS3 ensemble',
            record_summary='Two input protein chains: ' + '; '.join(f'{c["description"]} ({len(c["sequence"])} residues)' for c in plan['chains']) + '.',
            project_writeup=dict(status='input and analysis scope documented', biological_relevance='',
                ensemble_interpretation='All 1,000 original samples are retained. Energy colors annotate the complete construct and do not alter clustering.', project_citations=[]), references=[],
            provenance=dict(analysis_sequence_sha256=plan['sequence_sha256']))
        status[target] = dict(models=1000, residues=plan['residues'], clusters=len(colors), energy_ready=ready,
                              **({'hdbscan_clusters': result['clusters'], 'hdbscan_noise': result['noise_models']} if density else {}))
    write(output / 'atlas.json', {'targets': atlas})
    write(output / 'target-context.json', dict(verified_on='2026-11-02', targets=context))
    write(output / 'clustering-residues.json', dict(schema_version=1, targets=residue_catalog))
    for filename in ('residue-ranges.json', 'projection-metadata.json', 'supplementary-metadata.json', 'metric-overlays.json'):
        write(output / filename, {})
    write(output / 'selection-highlights.json', dict(schema_version=1, enabled=False, targets={}))
    if not all(entry['energy_ready'] for entry in status.values()):
        page = output / 'index.html'
        text = page.read_text().replace('<nav id="targets"',
            '<p class="hint" role="status">ProteinEBM scoring is queued. Its Color by option remains unavailable until all scores pass acceptance; no energy values are imputed.</p><nav id="targets"')
        page.write_text(text)
    page = output / 'index.html'
    text = page.read_text()
    for relative in [*ASSETS, 'assets/plotly.min.js', 'assets/3Dmol-min.js']:
        if relative.endswith(('.js', '.css')):
            text = text.replace('"'+relative+'"', '"'+relative+'?v='+sha(output/relative)[:12]+'"')
    page.write_text(text)
    validate_views(output, {p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()})
    (output / 'README.md').write_text('# ' + args.title + '\n\nAll 2,000 archived AFSample3 models, separate all-residue PCA/UMAP/t-SNE analyses, and exact original coordinates.\n\nProteinEBM colors appear only after acceptance of all scores for the construct. Learned arbitrary units; lower within construct.\n\nThe saved-atlas interface is generated from Structure_Clustering. Plotly.js and 3Dmol.js provide plotting and molecular display.\n')
    write(output.parent / (output.name + '-verification.json'), dict(status='verified', targets=status,
          files=[dict(path=p.relative_to(output).as_posix(), bytes=p.stat().st_size, sha256=sha(p))
                 for p in sorted(output.rglob('*')) if p.is_file()]))
    print(json.dumps(status, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--vendor-assets', type=Path, required=True)
    parser.add_argument('--title', default='CDK2–DOC1 structural atlas')
    parser.add_argument('--scores', type=Path)
    parser.add_argument('--density-results', type=Path)
    parser.add_argument('--density-plan', type=Path)
    parser.add_argument('--bonsai-results', type=Path)
    parser.add_argument('--bonsai-plan', type=Path)
    export(parser.parse_args())
