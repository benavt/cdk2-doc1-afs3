/* Shared population stays fixed; filters select medoid rows and fade plot points. */
let familyPrefix='',chosenClusters=null,filterCSV=null,pairSelecting=false,pairViewers=[],pairSerial=0;
function visibleCluster(label){return (!familyPrefix||label===familyPrefix||label.startsWith(familyPrefix+'.'))&&(!chosenClusters||chosenClusters.has(label))}
function configureRefinementControls(){
 familyPrefix='';chosenClusters=null;$('pairSection').hidden=true;
 const ancestors=new Set();for(const label of data.clusters){if(label.endsWith('.unassigned'))continue;const parts=label.split('.');for(let i=1;i<=parts.length;i++)ancestors.add(parts.slice(0,i).join('.'))}
 $('family').replaceChildren(Object.assign(document.createElement('option'),{value:'',textContent:'All current clusters'}),...[...ancestors].sort((a,b)=>a.localeCompare(b,undefined,{numeric:true})).map(label=>Object.assign(document.createElement('option'),{value:label,textContent:label+' and descendants'})));
 function options(){const labels=data.representatives.map(x=>x.cluster).filter(label=>!familyPrefix||label===familyPrefix||label.startsWith(familyPrefix+'.'));$('clusterSubset').replaceChildren(...labels.map(label=>Object.assign(document.createElement('option'),{value:label,textContent:label,selected:true})));chosenClusters=null}
 options();$('family').onchange=()=>{familyPrefix=$('family').value;options();scheduleDraw().catch(fail)};
 $('clusterSubset').onchange=()=>{const selected=[...$('clusterSubset').selectedOptions].map(x=>x.value);if(!selected.length){options()}else chosenClusters=new Set(selected);scheduleDraw().catch(fail)};
 $('allClusters').onclick=()=>{options();scheduleDraw().catch(fail)};
 $('decisionsPanel').hidden=!!data.visible_view_policy||!['whole','bounded'].includes(data.view_id||'whole')||!data.decisions;
 for(const link of document.querySelectorAll?.('.page-index a[href="#decisionsPanel"]')||[])link.hidden=$('decisionsPanel').hidden;
 $('boundedSummary').textContent=data.bounded_summary||'';$('decisionRows').replaceChildren();
 for(const row of data.decisions||[]){const tr=document.createElement('tr');const aris=Object.values(row.repeat_seed_ari||{}),tm=(row.tm_validation||[]).map(x=>x.median_margin);const fmt=x=>Number.isFinite(x)?x.toFixed(3):'—';for(const value of [row.parent,row.population,row.status,(row.child_sizes||[]).join(' / '),fmt(aris.length?Math.min(...aris):null),fmt(row.feature_silhouette),fmt(tm.length?Math.min(...tm):null),(row.reasons||[]).join(', ')]){const td=document.createElement('td');td.textContent=String(value??'—');tr.append(td)}$('decisionRows').append(tr)}
 $('waveRows').replaceChildren();for(const row of data.wave_summary||[]){const tr=document.createElement('tr');for(const value of [row.wave,row.expanded.join(', ')||'Original',row.clusters]){const td=document.createElement('td');td.textContent=String(value);tr.append(td)}$('waveRows').append(tr)}
}
function updateFilterDisplay(){
 for(const row of $('clusterRows').children)row.hidden=!visibleCluster(row.dataset.cluster);
 const groups=data.representatives.filter(x=>visibleCluster(x.cluster));const count=data.clusters.filter(visibleCluster).length;
 $('filterNote').textContent=`${groups.length} represented clusters selected; ${count.toLocaleString()} models in scope. All ${data.models.length.toLocaleString()} model points remain available; outside points are faded. Heat-map filtering reuses saved TM scores.`;
}
function filteredMedoidGrid(){
 const original=data.medoid_tm;if(!original)return null;
 const indices=original.labels.map((label,i)=>visibleCluster(label)?i:-1).filter(i=>i>=0),labels=indices.map(i=>original.labels[i]);
 const grid={...original,labels,matrix:indices.map(i=>indices.map(j=>original.matrix[i][j]))};
 if(filterCSV)URL.revokeObjectURL(filterCSV);
 const csv=[['cluster',...labels].join(','),...labels.map((label,i)=>[label,...grid.matrix[i]].join(','))].join('\n')+'\n';
 filterCSV=URL.createObjectURL(new Blob([csv],{type:'text/csv'}));grid.csv=filterCSV;$('medoidTMCsv').download=data.target+'_'+(data.range_id||'all')+'_'+data.view_id+'_selected_medoid_TM.csv';return grid;
}
async function chooseMedoidPair(left,right,value){
 const current=data,serial=++pairSerial;
 pairSelecting=true;try{await choose(left)}finally{pairSelecting=false}
 const active=()=>serial===pairSerial&&current===data&&selected===left;
 if(!active())return;
 $('pairSection').hidden=false;$('pairSection').open=true;$('pairScore').textContent=`${left} versus ${right} · TM similarity ${value.toFixed(4)} · medoids of the displayed ensembles`;
 if(!pairViewers.length)pairViewers=[$3Dmol.createViewer($('pairLeft'),{backgroundColor:'white'}),$3Dmol.createViewer($('pairRight'),{backgroundColor:'white'})];
 for(const [i,label]of [left,right].entries()){
  const c=current.representatives.find(x=>x.cluster===label);if(!c)throw Error('Missing medoid descriptor');let text=c.coordinate_text;
  if(!text){const r=await fetch(c.file,{signal:AbortSignal.timeout(15000)});if(!r.ok)throw Error('Medoid file unavailable');text=await r.text();c.coordinate_text=text}
  if(!active())return;const v=pairViewers[i];v.removeAllModels();v._aisModels=[v.addModel(text,c.format)];v._aisDescriptor=c;styleSavedStructure(v,c.color);v.resize();fitVisibleStructure(v);
 }
 frameMedoidPair();
}

'use strict';
let atlas,data,viewer,selected=null,selectedModelIndex=null,spinning=false,loadSerial=0,targetRequest=0,modelDownloadURL=null,ensembleDownloadURL=null;
let projectionLegendKey='',renderQueue=Promise.resolve(),metricOverlayLoader=null;
let selectionLoader=null,selectionPayload=null,selectionPreference={method:'panel',alpha:.5,tau_multiplier:1,replicate:1},selectionHighlight={active:false,indices:new Set(),orderedIndices:[]},selectionResult={status:'unavailable',note:''},selectionLoading=true,selectionRenderSerial=0;
const hiddenProjectionCategories=new Set();
const $=id=>document.getElementById(id), escapeText=x=>String(x).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
async function json(url){let r;try{r=await fetch(url,{cache:'no-cache',signal:AbortSignal.timeout(30000)})}catch(error){throw Error('The atlas service is unavailable. Reopen the local atlas or request a fresh private preview; models in an already loaded analysis remain available.')}if(!r.ok)throw Error(`Could not load ${url}: ${r.status}`);return r.json()}
function fail(error){setAnalysisLoading(false);window.AtlasExplorer?.setBusy(false);$('error').hidden=false;$('error').textContent=error.message||String(error);console.error(error)}
let clusteringResidueCatalog={},structureScopePreference='clustering',structureMappingError='';
let supplementaryMetadataCatalog={},savedHeatmapSpecs=[];
async function fetchOptionalJSON(path){
 try{const response=await fetch(path,{cache:'no-cache',signal:AbortSignal.timeout(15000)});return response.ok?await response.json():{}}catch(error){return {}}
}
async function fetchClusteringResidues(){return fetchOptionalJSON('clustering-residues.json')}
function withoutUnavailableRefolds(current){const retired=new Set(['boltz2_exact_refold_ptm','boltz2_exact_refold_mean_plddt','boltz2_exact_refold_template_tm']);return {...current,schemes:current.schemes.filter(s=>!retired.has(s.key)||s.unavailable!==true||!Array.isArray(s.values)||s.values.length!==current.models.length||!s.values.every(v=>v===null))}}
function updateMetricOverlayNote(){const node=$('overlayMetricNote');if(!node)return;const note=typeof AISExplorerMetrics!=='undefined'?AISExplorerMetrics.note(data,$('color').value):'';node.hidden=!note;node.textContent=note;}
function updateSelectionControls(){
 const method=$('selectionMethod');if(!method)return;
 if(typeof AISExplorerSelections==='undefined'){if($('selectionControls'))$('selectionControls').hidden=true;return}
 if($('selectionControls'))$('selectionControls').hidden=selectionLoader?.enabled===false;
 const available=!!selectionPayload&&!selectionLoading;
 method.disabled=!available;method.value=available?selectionPreference.method:'none';
 for(const [id,value]of [['selectionBalance',selectionPreference.alpha],['selectionPressure',selectionPreference.tau_multiplier],['selectionReplicate',selectionPreference.replicate]]){const node=$(id);if(!node)continue;node.value=String(value);node.disabled=!available||(['selectionBalance','selectionPressure'].includes(id)?!['panel','exact','mh'].includes(selectionPreference.method):!['panel','uniform'].includes(selectionPreference.method))}
 const note=$('selectionStatus');if(note){note.textContent=selectionLoading?'Loading verified saved selections…':selectionPayload?selectionHighlight.note||'':selectionResult.note||'No saved selection highlights are available for this analysis.';if(selectionHighlight.active&&data){const visible=selectionHighlight.orderedIndices.filter(i=>visibleCluster(data.clusters[i])&&!hiddenProjectionCategories.has(AISExplorerSelections.category(scheme(),i))).length;if(visible!==selectionHighlight.indices.size)note.textContent+=' '+visible.toLocaleString()+' highlighted models remain visible after filters.'}}
}
function refreshSelectionHighlight(){
 try{selectionHighlight=typeof AISExplorerSelections!=='undefined'?AISExplorerSelections.select(selectionPayload,selectionPreference):{active:false,indices:new Set(),orderedIndices:[]}}
 catch(error){selectionPayload=null;selectionHighlight={active:false,indices:new Set(),orderedIndices:[]};selectionResult={status:'unavailable',note:error.message}}
 updateSelectionControls();
}
function clearSamplingHighlight(){selectionPayload=null;selectionHighlight={active:false,indices:new Set(),orderedIndices:[]};selectionResult={status:'loading',note:''};++selectionRenderSerial;}
function selectionProjectionTraces(method){const rows=traces(method);if(typeof AISExplorerSelections==='undefined')return rows;const overlay=AISExplorerSelections.overlayTrace(data,method,selectionHighlight,scheme(),visibleCluster,hiddenProjectionCategories);return overlay?[...rows,overlay]:rows;}
function scheduleSelectionDraw(){const request=targetRequest,serial=++selectionRenderSerial;renderQueue=renderQueue.catch(()=>{}).then(async()=>{if(request!==targetRequest||serial!==selectionRenderSerial)return;await drawProjections();if(request===targetRequest&&serial===selectionRenderSerial)await drawBonsai()});return renderQueue;}
function readSelectionRoute(){if(typeof AISExplorerSelections!=='undefined'){const query=decodeURIComponent(location.hash.slice(1)).split('?')[1]||'';selectionPreference=AISExplorerSelections.parseSettings(new URLSearchParams(query),selectionPreference)}}
function changeSavedSelection(){
 selectionPreference={method:$('selectionMethod').value,alpha:Number($('selectionBalance').value),tau_multiplier:Number($('selectionPressure').value),replicate:Number($('selectionReplicate').value)};refreshSelectionHighlight();
 window.history?.replaceState(null,'','#'+analysisHash(data.target,data.range_id,data.policy_view_id||data.view_id));scheduleSelectionDraw().catch(fail);
}
function clusteringResidues(current=data){
 const target=clusteringResidueCatalog.targets?.[current.target],range=current.range_id||'all',entry=target?.ranges?.[range]?.views?.[current.view_id||'whole']||(range==='all'?target?.views?.[current.view_id||'whole']:null);
 if(!entry||typeof entry.chain!=='string'||!Number.isInteger(entry.expected_ca_count)||entry.expected_ca_count<1||!Array.isArray(entry.canonical_positions)||!entry.canonical_positions.length)return null;
 const positions=entry.canonical_positions;
 if(positions.some(p=>!Number.isInteger(p)||p<1||p>entry.expected_ca_count)||new Set(positions).size!==positions.length)return null;
 return entry;
}
function verifiedRegions(meta){
 if(!meta?.regions_verified||!Array.isArray(meta.regions)||!meta.regions.length)return [];
 const used=new Set();for(const region of meta.regions){if(typeof region.label!=='string'||!/^#[0-9a-f]{6}$/i.test(region.color)||!Number.isInteger(region.start)||!Number.isInteger(region.end)||region.start<1||region.end<region.start||region.end>meta.expected_ca_count)return [];for(let p=region.start;p<=region.end;p++){if(used.has(p))return [];used.add(p)}}
 return meta.regions;
}
function setStructureOption(id,value,enabled){const option=Array.from($(id).options||[]).find(o=>o.value===value);if(option){option.disabled=!enabled;if(id==='structureColor'&&value==='regions')option.textContent=enabled?'Regions':'Regions — unavailable'}}
function configureModelMode(cluster=null){
 const available=cluster?!!(cluster.ensemble_file||cluster.ensemble_text):data.representatives.some(row=>row.ensemble_file||row.ensemble_text),option=Array.from($('modelMode').options||[]).find(row=>row.value==='ensemble');
 if(option){option.disabled=!available;option.textContent=available?'Comparison ensemble':'Comparison ensemble — unavailable'}
 if(!available)$('modelMode').value='medoid';
}
function configureStructureControls(){
 const meta=clusteringResidues();structureMappingError='';
 setStructureOption('structureScope','clustering',!!meta);setStructureOption('structureColor','rainbow',!!meta);setStructureOption('structureColor','regions',!!verifiedRegions(meta).length);setStructureOption('structureColor','plddt',data.structure_confidence?.kind==='plddt');
 $('structureScope').value=meta?structureScopePreference:'full';
 if((!meta&&['rainbow','regions'].includes($('structureColor').value))||($('structureColor').value==='regions'&&!verifiedRegions(meta).length)||($('structureColor').value==='plddt'&&data.structure_confidence?.kind!=='plddt'))$('structureColor').value='cluster';
 updateStructureScopeNote();
 if(structureViewAnchor&&structureViewAnchor.context!==structureViewContext())clearStructureView('The view was released because the target or clustering residue range changed.');
}
function updateStructureScopeNote(){
 const meta=clusteringResidues(),regions=verifiedRegions(meta),mode=$('structureColor').value;
 let note=meta?`Clustering uses ${meta.canonical_positions.length} canonical residues: ${meta.reference_ranges||meta.canonical_positions.join(', ')}. ${meta.note||''}`:'The exact clustering residue map is unavailable for this saved view. Only the full saved structure can be displayed; no residue clipping is inferred.';
 if(meta?.analysis_uses_full_construct)note+=' Every supplied construct residue was used; no residues were excluded, so Clustering residues and Full saved structure show the same coordinates for this analysis.';
 if(structureMappingError)note+=' '+structureMappingError;
 if(mode==='rainbow')note+=' Rainbow follows canonical chain order, blue at the N terminus to red at the C terminus.';
 if(mode==='chains')note+=' Chain A is green; chain B is cyan. Other chains are gray.';
 if(mode==='plddt')note+=' Reported per-atom pLDDT: dark blue ≥90, light blue 70–90, yellow 50–70, orange <50. Missing observations are gray.';
 if(mode==='regions'&&!regions.length)note+=' Verified saved variance-region labels are unavailable.';
 note+=' Display controls do not alter saved coordinates or downloads; downloads contain the full saved structures.';
 $('structureScopeNote').textContent=note;
 const legend=$('structureRegionLegend');legend.replaceChildren();
 const entries=mode==='chains'?[{label:'Chain A',color:'#008000'},{label:'Chain B',color:'#00ffff'}]:mode==='plddt'?[{label:'pLDDT ≥90',color:'#0053d6'},{label:'70–90',color:'#65cbf3'},{label:'50–70',color:'#ffdb13'},{label:'<50',color:'#ff7d45'}]:mode==='regions'&&regions.length?[...regions,{label:'Other residues',color:'#aebbc1'}]:[];
 legend.hidden=!entries.length;
 for(const r of entries){const item=document.createElement('span'),swatch=document.createElement('i');swatch.style.backgroundColor=r.color;item.append(swatch,document.createTextNode(r.label+(r.start?' · '+r.start+'–'+r.end:'')));legend.append(item)}
 if(mode==='regions'&&regions.length){const caption=document.createElement('p');caption.textContent='Regions are automated labels from the saved structural-variance analysis; they are not confirmed biological domains.'+(meta.regions_note?' '+meta.regions_note:'');legend.append(caption)}
}
function residueIdentity(atom){return String(atom.chain??'')+'|'+String(atom.resi)+'|'+String(atom.icode??'').trim()}
function canonicalCAAtoms(model,meta){
 if(!Array.isArray(meta.chains))return model.selectedAtoms({atom:'CA',chain:meta.chain});
 if(!meta.chains.length||new Set(meta.chains.map(c=>c.chain)).size!==meta.chains.length||meta.chains.some(c=>typeof c.chain!=='string'||!Number.isInteger(c.expected_ca_count)||c.expected_ca_count<1))throw Error('Invalid ordered chain residue map.');
 const atoms=meta.chains.flatMap(chain=>{const ca=model.selectedAtoms({atom:'CA',chain:chain.chain});if(ca.length!==chain.expected_ca_count)throw Error('Chain '+chain.chain+' does not match its verified residue count.');return ca});
 if(model.selectedAtoms({atom:'CA'}).length!==atoms.length||atoms.length!==meta.expected_ca_count)throw Error('The complete multi-chain structure differs from its verified residue map.');return atoms;
}
function canonicalResidueMap(model,meta){
 const ca=canonicalCAAtoms(model,meta);
 if(ca.length!==meta.expected_ca_count)throw Error(`This frame has ${ca.length} Cα residues on chain ${meta.chain||'(blank)'}, while the verified canonical map requires ${meta.expected_ca_count}.`);
 const map=new Map();for(const [i,atom]of ca.entries()){const key=residueIdentity(atom);if(map.has(key))throw Error('This frame has duplicate residue identities; its canonical residue mapping is ambiguous.');map.set(key,i+1)}return map;
}
function canonicalRainbow(position,count){
 // Blue N terminus -> cyan -> green -> yellow -> red C terminus, stable across raw PDB numbering.
 const h=240*(1-(position-1)/Math.max(1,count-1)),x=1-Math.abs((h/60)%2-1);let rgb;
 if(h<60)rgb=[1,x,0];else if(h<120)rgb=[x,1,0];else if(h<180)rgb=[0,1,x];else rgb=[0,x,1];
 return rgb.reduce((out,c)=>(out<<8)+Math.round(c*255),0);
}
function styleSavedStructure(target,color,opacity=1){
 const meta=clusteringResidues(),scope=$('structureScope').value||'full',mode=$('structureColor').value||'cluster',regions=verifiedRegions(meta),models=target._aisModels?.filter(Boolean);
 if(!models?.length){if(scope==='clustering'||mode!=='cluster'){target.setStyle({},{});structureMappingError='Frame handles are unavailable, so the verified residue selection cannot be applied. Choose Full saved structure with Cluster color.';updateStructureScopeNote();return false}target.setStyle({},{cartoon:{color,opacity}});return true}
 const mappingNeeded=scope==='clustering'||['rainbow','regions'].includes(mode);let maps=[];
 try{if(mappingNeeded){if(!meta)throw Error('No verified canonical residue map is available.');if(mode==='regions'&&!regions.length)throw Error('No verified structural-variance regions are available.');maps=models.map(model=>canonicalResidueMap(model,meta))}}
 catch(error){models.forEach(model=>model.setStyle({},{}));structureMappingError=error.message+' Choose Full saved structure with Cluster color to inspect the original coordinates.';updateStructureScopeNote();return false}
 const kept=new Set(meta?.canonical_positions||[]);
 for(const [i,model]of models.entries()){
  const positions=maps[i],cartoon={color,opacity};
  if(mode==='plddt'&&data.structure_confidence?.kind!=='plddt'){structureMappingError='Reported pLDDT observations are unavailable for this dataset.';updateStructureScopeNote();return false}
  if(mode==='chains')cartoon.colorfunc=atom=>atom.chain==='A'?'#008000':atom.chain==='B'?'#00ffff':'#aebbc1';
  else if(mode==='plddt')cartoon.colorfunc=atom=>{const value=atom.b;if(typeof value!=='number'||!Number.isFinite(value)||value<0||value>100)return '#aebbc1';return value>=90?'#0053d6':value>=70?'#65cbf3':value>=50?'#ffdb13':'#ff7d45'};
  else if(mode!=='cluster')cartoon.colorfunc=atom=>{const position=positions.get(residueIdentity(atom));if(position===undefined)return '#aebbc1';if(mode==='rainbow')return canonicalRainbow(position,meta.expected_ca_count);return regions.find(r=>position>=r.start&&position<=r.end)?.color||'#aebbc1'};
  model.setStyle({},{});model.setStyle(scope==='clustering'?{predicate:atom=>kept.has(positions.get(residueIdentity(atom)))}:{},{cartoon});
 }
 structureMappingError='';updateStructureScopeNote();return true;
}
function fitVisibleStructure(target){target.zoomTo({predicate:atom=>!!atom.style?.cartoon});target.render()}
let structureViewAnchor=null,structureViewMessage='';
function structureViewContext(){
 const meta=clusteringResidues();return meta?JSON.stringify([data.target,data.range_id||'all',meta.chain,meta.chains,meta.sequence_sha256,meta.expected_ca_count,meta.canonical_positions]):null;
}
function structureViewPoints(model){
 const meta=clusteringResidues();if(!meta)throw Error('The clustering residue map is unavailable.');
 canonicalResidueMap(model,meta);
 const ca=canonicalCAAtoms(model,meta),points=meta.canonical_positions.map(p=>{const a=ca[p-1];return [a.x,a.y,a.z]});
 if(points.length<3||points.some(p=>p.some(v=>!Number.isFinite(v))))throw Error('At least three valid clustering Cα residues are required.');
 return points;
}
function transformViewPoint(point,fit){return fit.rotation.map((row,i)=>row.reduce((sum,value,j)=>sum+value*point[j],fit.translation[i]))}
function rigidViewFit(mobile,reference){
 // Horn's unit-quaternion fit: a proper rigid rotation, without reflection,
 // rescaling, outlier removal or changes to the saved coordinate text.
 if(mobile.length!==reference.length||mobile.length<3||[...mobile,...reference].some(p=>p.length!==3||p.some(v=>!Number.isFinite(v))))throw Error('The clustering residue coordinates do not match.');
 const center=points=>[0,1,2].map(i=>points.reduce((sum,p)=>sum+p[i],0)/points.length),mc=center(mobile),rc=center(reference);
 const centered=(points,c)=>points.map(p=>p.map((v,i)=>v-c[i])),x=centered(mobile,mc),y=centered(reference,rc);
 for(const points of [x,y]){
  const lengths=points.map(p=>p.reduce((sum,v)=>sum+v*v,0)),axis=points[lengths.indexOf(Math.max(...lengths))],scale=Math.max(...lengths);
  const area=Math.max(...points.map(p=>[axis[1]*p[2]-axis[2]*p[1],axis[2]*p[0]-axis[0]*p[2],axis[0]*p[1]-axis[1]*p[0]].reduce((sum,v)=>sum+v*v,0)));
  if(!Number.isFinite(scale)||!Number.isFinite(area)||scale<1e-12||area<1e-12*scale*scale)throw Error('The clustering residues cannot define a stable orientation.');
 }
 const s=[0,1,2].map(i=>[0,1,2].map(j=>x.reduce((sum,p,k)=>sum+p[i]*y[k][j],0)));
 const [[a,b,c],[d,e,f],[g,h,i]]=s;
 const n=[[a+e+i,f-h,g-c,b-d],[f-h,a-e-i,b+d,c+g],[g-c,b+d,-a+e-i,f+h],[b-d,c+g,f+h,-a-e+i]],v=Array.from({length:4},(_,r)=>Array.from({length:4},(_,c)=>Number(r===c)));
 if(n.flat().some(value=>!Number.isFinite(value)))throw Error('The structure alignment is not finite.');
 for(let sweep=0;sweep<64;sweep++){
  let p=0,q=1;for(let r=0;r<4;r++)for(let c=r+1;c<4;c++)if(Math.abs(n[r][c])>Math.abs(n[p][q])){p=r;q=c}
  if(Math.abs(n[p][q])<1e-13*Math.max(1,...n.map((row,r)=>Math.abs(row[r]))))break;
  const angle=.5*Math.atan2(2*n[p][q],n[q][q]-n[p][p]),cs=Math.cos(angle),sn=Math.sin(angle),pp=n[p][p],qq=n[q][q],pq=n[p][q];
  for(let r=0;r<4;r++)if(r!==p&&r!==q){const rp=n[r][p],rq=n[r][q];n[r][p]=n[p][r]=cs*rp-sn*rq;n[r][q]=n[q][r]=sn*rp+cs*rq}
  n[p][p]=cs*cs*pp-2*sn*cs*pq+sn*sn*qq;n[q][q]=sn*sn*pp+2*sn*cs*pq+cs*cs*qq;n[p][q]=n[q][p]=0;
  for(let r=0;r<4;r++){const rp=v[r][p],rq=v[r][q];v[r][p]=cs*rp-sn*rq;v[r][q]=sn*rp+cs*rq}
 }
 const largest=n.map((row,r)=>row[r]),column=largest.indexOf(Math.max(...largest)),quaternion=v.map(row=>row[column]),norm=Math.hypot(...quaternion),[w,qx,qy,qz]=quaternion.map(value=>value/norm);
 const rotation=[[1-2*(qy*qy+qz*qz),2*(qx*qy-qz*w),2*(qx*qz+qy*w)],[2*(qx*qy+qz*w),1-2*(qx*qx+qz*qz),2*(qy*qz-qx*w)],[2*(qx*qz-qy*w),2*(qy*qz+qx*w),1-2*(qx*qx+qy*qy)]];
 const translation=rc.map((value,r)=>value-rotation[r].reduce((sum,value,c)=>sum+value*mc[c],0));
 if([...rotation.flat(),...translation].some(value=>!Number.isFinite(value)))throw Error('The structure alignment is not finite.');
 return {rotation,translation};
}
function updateStructureViewControls(){
 const button=$('setStructureView');if(!button)return;
 const available=!!viewer?._aisModels?.length&&!!structureViewContext();
 button.disabled=!available;button.setAttribute('aria-pressed',String(!!structureViewAnchor));button.textContent=structureViewAnchor?'Release view':'Set view';
 button.title=structureViewAnchor?'Return to automatic framing for new selections':'Align new selections to this model and keep the camera view';
 $('structureHint').textContent='Drag to rotate · scroll or pinch to zoom. '+(structureViewMessage||(structureViewAnchor?'View set to '+structureViewAnchor.label+(structureViewAnchor.ensemble?' (first ensemble frame)':'')+'. New selections align using the clustering residues. Reset view restores the saved camera.':'Set view keeps models aligned while you select other clusters.'));
}
function clearStructureView(message=''){
 structureViewAnchor=null;structureViewMessage=message;updateStructureViewControls();
}
function structureCamera(){return {view:viewer.getView().slice(),slab:{...viewer.getSlab()}}}
function setStructureView(){
 if(structureViewAnchor){clearStructureView();return}
 try{
  const reference=structureViewPoints(viewer._aisModels[0]),camera=structureCamera();rigidViewFit(reference,reference);
  if(camera.view.length!==8||[...camera.view,camera.slab.near,camera.slab.far].some(value=>!Number.isFinite(value)))throw Error('The current camera is unavailable.');
  structureViewAnchor={context:structureViewContext(),reference,camera,activeCamera:camera,label:selected,ensemble:viewer._aisEnsemble};structureViewMessage='';
  spinning=false;viewer.spin(false);$('spin').setAttribute('aria-pressed','false');$('spin').textContent='Rotate';
 }catch(error){structureViewMessage='Could not set view: '+error.message}
 updateStructureViewControls();
}
function alignStructureToSetView(){
 if(!structureViewAnchor)return false;
 if(structureViewAnchor.context!==structureViewContext()){clearStructureView('The view was released because the target or clustering residue range changed.');return false}
 try{
  // Validate every frame before changing any displayed atoms. The original
  // coordinate strings remain the source for all model/ensemble downloads.
  if(!viewer._aisModels?.length)throw Error('No displayed structure frame is available.');
  const frames=viewer._aisModels.map(model=>{
   const fit=rigidViewFit(structureViewPoints(model),structureViewAnchor.reference),atoms=model.selectedAtoms({});
   const coordinates=atoms.map(atom=>transformViewPoint([atom.x,atom.y,atom.z],fit));
   if(coordinates.some(p=>p.some(v=>!Number.isFinite(v))))throw Error('A displayed frame has invalid coordinates.');
   return {atoms,coordinates};
  });
  for(const {atoms,coordinates} of frames)for(const [i,atom]of atoms.entries())[atom.x,atom.y,atom.z]=coordinates[i];
  return true;
 }catch(error){clearStructureView('The view was released: '+error.message);return false}
}
function frameSelectedStructure(camera=null){
 if(structureViewAnchor){const saved=camera||structureViewAnchor.activeCamera;viewer.setSlab(saved.slab.near,saved.slab.far);viewer.setView(saved.view);structureViewAnchor.activeCamera=saved;viewer.render()}else fitVisibleStructure(viewer);
 updateStructureViewControls();
}
function frameMedoidPair(){
 if(pairViewers.length!==2||!pairViewers[1]._aisDescriptor)return;
 const descriptor=pairViewers[1]._aisDescriptor,ghost=pairViewers[0].addModel(descriptor.coordinate_text,descriptor.format),original=pairViewers[0]._aisModels;
 pairViewers[0]._aisModels=[ghost];styleSavedStructure(pairViewers[0],descriptor.color);pairViewers[0]._aisModels=original;
 fitVisibleStructure(pairViewers[0]);const common=pairViewers[0].getView();pairViewers[0].removeModel(ghost);pairViewers.forEach(v=>{v.setView(common);v.render()});$('pairReset').onclick=()=>pairViewers.forEach(v=>{v.setView(common);v.render()});
}
function restyleStructureViews(){
 if(viewer._aisDescriptor){const camera=structureViewAnchor?structureCamera():null;styleSavedStructure(viewer,viewer._aisDescriptor.color,viewer._aisEnsemble ? .62 : 1);frameSelectedStructure(camera)}
 for(const v of pairViewers)if(!$('pairSection').hidden&&v._aisDescriptor){styleSavedStructure(v,v._aisDescriptor.color);fitVisibleStructure(v)}
 if(!$('pairSection').hidden)frameMedoidPair();updateStructureScopeNote();
}
let projectionMetadataCatalog={schema_version:1,targets:{}};
function projectionAxisTitles(method,projection,current=data){
 if(method!=='pca')return projection.axes;
 const range=current.range_id||'all',saved=projectionMetadataCatalog.targets?.[current.target]?.ranges?.[range]?.views?.[current.view_id||'whole']?.pca;
 let ratio=saved?.explained_variance_ratio??projection.explained_variance_ratio;
 const scope=saved?.scope_label||projection.scope_label||projection.axes?.[0]?.split(' · ').slice(1).join(' · ');
 if(ratio===undefined||ratio===null){
  const legacy=(projection.axes||[]).map(text=>String(text).match(/PC(?:A)?\s*[12]\s*\(\s*([0-9]+(?:\.[0-9]+)?)\s*%(?:[^)]*)\)/i));
  if(legacy.length===2&&legacy.every(Boolean))ratio=legacy.map(match=>Number(match[1])/100);
 }
 const valid=Array.isArray(ratio)&&ratio.length===2&&ratio.every(value=>typeof value==='number'&&Number.isFinite(value)&&value>=0&&value<=1)&&ratio.reduce((a,b)=>a+b,0)<=1.000001;
 return [0,1].map(i=>'PC'+(i+1)+(valid?' ('+(100*ratio[i]).toFixed(1)+'% variance explained)':' (variance unavailable)')+(scope?' · '+scope:''));
}
function referenceSimilarity(rep){const score=data.schemes.find(s=>s.key==='tm_colabfold12_rank1_chainA_res5_95'),value=score?.values[data.models.indexOf(rep.model)];return Number.isFinite(rep.tm_to_reference)?rep.tm_to_reference:Number.isFinite(value)?value:null}
function population(count){const percent=100*count/data.models.length;return percent<.1?'<0.1%':percent.toFixed(1)+'%'}
function scheme(){return data.schemes.find(x=>x.key===$('color').value)}
function traces(method){
 const s=scheme(),xy=data.projections[method].xy,out=[],groups=new Map();
 data.models.forEach((name,i)=>{const v=s.values[i],key=s.type==='continuous'?(Number.isFinite(v)?'valid':'Not calculable'):String(v??'Unspecified');if(!groups.has(key))groups.set(key,[]);groups.get(key).push(i)});
 for(const [label,indices] of groups){const numeric=s.type==='continuous'&&label==='valid',marker={size:4.5,opacity:indices.map(i=>visibleCluster(data.clusters[i])?(selectionHighlight.active?(selectionHighlight.indices.has(i) ? .85 : .09):.7):.06)};
  if(numeric)Object.assign(marker,{color:indices.map(i=>s.values[i]),colorscale:s.colorscale,cmin:s.range?.[0],cmax:s.range?.[1],showscale:false,colorbar:{title:{text:s.short_name||s.name},thickness:10,len:.7}});
  else marker.color=s.type==='continuous'?'#808080':s.colors[label]||'#808080';
  out.push({type:'scattergl',mode:'markers',name:label==='valid'?s.name:label,x:indices.map(i=>xy[i][0]),y:indices.map(i=>xy[i][1]),customdata:indices,text:indices.map(i=>`${escapeText(data.models[i])}<br>${escapeText(data.clusters[i])}<br>${escapeText(data.methods[i])}${numeric?'<br>'+s.name+': '+s.values[i].toFixed(2):''}`),hovertemplate:'%{text}<extra></extra>',marker,meta:{legendKey:label,numeric},visible:hiddenProjectionCategories.has(label)?'legendonly':true,showlegend:false});
 }if(s.type==='continuous')out.sort((a,b)=>Number(a.meta.numeric)-Number(b.meta.numeric));return out;
}
function projectionLegendTraces(){
 const s=scheme();
 return traces('pca').map(trace=>{
  const marker={...trace.marker,size:8,opacity:1};
  if(trace.meta.numeric){
   const finite=s.values.filter(Number.isFinite),range=s.range||[Math.min(...finite),Math.max(...finite)];
   Object.assign(marker,{color:range,showscale:true,cmin:range[0],cmax:range[1],colorbar:{title:{text:s.short_name||s.name},outlinewidth:0}});
  }
  return {type:'scatter',mode:'markers',name:trace.name,meta:trace.meta,x:trace.meta.numeric?[0,0]:[0],y:trace.meta.numeric?[0,0]:[0],marker,visible:trace.visible,showlegend:!trace.meta.numeric,hoverinfo:'skip'};
 });
}
function changeProjectionCategory(event,isolate=false){
 const trace=$('projectionLegend').data[event.curveNumber],key=trace?.meta?.legendKey;if(!key||trace.meta.numeric)return false;
 const keys=traces('pca').map(t=>t.meta.legendKey);
 if(isolate&&scheme().type!=='continuous'){
  const alreadyIsolated=keys.every(k=>hiddenProjectionCategories.has(k)===(k!==key));
  hiddenProjectionCategories.clear();if(!alreadyIsolated)for(const k of keys)if(k!==key)hiddenProjectionCategories.add(k);
 }else if(hiddenProjectionCategories.has(key))hiddenProjectionCategories.delete(key);else hiddenProjectionCategories.add(key);
 scheduleDraw().catch(fail);return false;
}
async function drawProjections(){
 const key=data.target+'|'+(data.range_id||'all')+'|'+(data.view_id||'whole')+'|'+scheme().key;
 if(projectionLegendKey!==key){projectionLegendKey=key;hiddenProjectionCategories.clear()}
 await Promise.all(['pca','umap','tsne'].map(async method=>{const p=data.projections[method],axes=projectionAxisTitles(method,p);await AtlasResponsive.react($(method),selectionProjectionTraces(method),{paper_bgcolor:'#fff',plot_bgcolor:'#fff',margin:{l:52,r:25,t:16,b:58},showlegend:false,hovermode:'closest',font:{family:'Arial, sans-serif',size:11,color:'#344f5b'},xaxis:{title:{text:axes[0]},zeroline:false,gridcolor:'#edf1f2'},yaxis:{title:{text:axes[1]},zeroline:false,gridcolor:'#edf1f2'},uirevision:data.target+'-'+(data.range_id||'all')+'-'+(data.view_id||'whole')+'-'+method},{responsive:true,displaylogo:false,modeBarButtonsToRemove:['lasso2d']});$(method).removeAllListeners('plotly_click');$(method).on('plotly_click',e=>{const i=e.points[0].customdata;if(Number.isInteger(i)&&i>=0&&i<data.models.length)(data.model_files?choose(data.clusters[i],i):choose(data.clusters[i])).catch(fail)})}));
 const legend=$('projectionLegend');const legendCount=projectionLegendTraces().length;const panel=$('legendPanel');if(panel.dataset.legendKey!==key){panel.dataset.legendKey=key;panel.open=legendCount<=16}$('legendSummary').textContent='Shared color legend · '+(scheme().short_name||scheme().name)+(legendCount>16?' · '+legendCount+' categories':'');
 await AtlasResponsive.react(legend,projectionLegendTraces(),{paper_bgcolor:'#fff',plot_bgcolor:'#fff',margin:{l:8,r:8,t:8,b:8},xaxis:{visible:false,range:[1,2],fixedrange:true},yaxis:{visible:false,range:[1,2],fixedrange:true},showlegend:true,legend:{orientation:'h',font:{size:12}},uirevision:projectionLegendKey},{displayModeBar:false,displaylogo:false,staticPlot:false});
 legend.removeAllListeners('plotly_legendclick');legend.removeAllListeners('plotly_legenddoubleclick');
 legend.on('plotly_legendclick',event=>changeProjectionCategory(event));
 legend.on('plotly_legenddoubleclick',event=>changeProjectionCategory(event,true));
 updateSelectionControls();showProjection();
}
async function draw(){
 window.AtlasExplorer?.setBusy(true);
 updateFilterDisplay();await drawProjections();await drawViolins();await drawDistanceMaps();await drawCandidateReview();await drawMedoidTM();await drawBonsai();window.AtlasExplorer?.setBusy(false);
}
function configureDistanceMaps(){
 const entry=supplementaryMetadataCatalog.targets?.[data.target]?.ranges?.[data.range_id||'all'];savedHeatmapSpecs=[];
 if(entry?.views?.[data.view_id||'whole']){
  const caption=document.createElement('p');caption.className='hint';caption.textContent=entry.sample_count.toLocaleString()+' models · canonical residues '+entry.positions[0]+'–'+entry.positions.at(-1)+'. '+entry.note;
  const plots=[['median_matrix','Median Cα distance (Å)','Viridis'],['variance_matrix','Cα distance variance (Å²)','Magma']].map(([key,name,scale])=>{const section=document.createElement('section'),title=document.createElement('h3'),node=document.createElement('div');title.textContent=name;node.id='saved-'+key;section.append(title,node);savedHeatmapSpecs.push({node,entry,key,name,scale});return section});
  $('heatmaps').replaceChildren(caption,...plots);return;
 }
 const images=(data.heatmaps||[]).map(p=>{const a=document.createElement('a');a.href=p.file;a.target='_blank';const img=document.createElement('img');img.src=p.file;img.alt=p.name;img.loading='lazy';a.append(img);return a});
 if(!images.length){const note=document.createElement('p');note.className='hint';note.textContent='Distance summaries for this residue range have not been added to this saved display.';images.push(note)}
 $('heatmaps').replaceChildren(...images);
}
async function drawDistanceMaps(){
 for(const {node,entry,key,name,scale} of savedHeatmapSpecs){const positions=entry.positions;await AtlasResponsive.react(node,[{type:'heatmap',x:positions,y:positions,z:entry[key],colorscale:scale,colorbar:{title:{text:name}},hovertemplate:'Residue %{y} / %{x}<br>%{z:.3f}<extra>'+escapeText(name)+'</extra>'}],{paper_bgcolor:'#fff',margin:{l:65,r:25,t:90,b:70},xaxis:{title:{text:'Canonical residue'}},yaxis:{title:{text:'Canonical residue'},autorange:'reversed'},uirevision:data.target+'-'+data.range_id+'-'+key},{displaylogo:false});}
}
function scheduleDraw(){const request=targetRequest;renderQueue=renderQueue.catch(()=>{}).then(()=>request===targetRequest?draw():undefined);return renderQueue}
async function drawViolins(){
 const score=data.schemes.find(s=>s.key==='tm_colabfold12_rank1_chainA_res5_95');$('tmDistribution').hidden=!score;if(!score)return;
 const traces=data.representatives.filter(c=>visibleCluster(c.cluster)).map(c=>{const indices=data.clusters.map((label,i)=>label===c.cluster?i:-1).filter(i=>i>=0),values=indices.map(i=>score.values[i]).filter(Number.isFinite),name=c.cluster+' · n='+values.length;if(values.length<2||new Set(values).size<2)return {type:'scatter',mode:'markers',name,x:[name],y:[values[0]],marker:{color:c.color,size:9},hovertemplate:'TM: %{y:.4f}<extra>'+escapeText(c.cluster)+'</extra>'};return {type:'violin',name,x:values.map(()=>name),y:values,customdata:indices.filter(i=>Number.isFinite(score.values[i])).map(i=>data.models[i]),text:indices.filter(i=>Number.isFinite(score.values[i])).map(i=>data.models[i]),line:{color:c.color,width:1.3},fillcolor:c.color,opacity:.75,box:{visible:true},meanline:{visible:false},points:false,spanmode:'hard',scalemode:'width',hovertemplate:'%{text}<br>TM: %{y:.4f}<extra>'+escapeText(c.cluster)+'</extra>'}});
 await AtlasResponsive.react($('tmViolin'),traces,{paper_bgcolor:'#fff',plot_bgcolor:'#fff',margin:{l:65,r:25,t:20,b:145},font:{family:'Arial, sans-serif',size:12,color:'#344f5b'},showlegend:false,yaxis:{title:{text:'TM-score to 12mer reference (5–95)'},range:[0,1],gridcolor:'#edf1f2'},xaxis:{type:'category',tickangle:-55,automargin:true},uirevision:data.target+'-'+(data.range_id||'all')+'-'+data.view_id+'-tm-violin'},{responsive:true,displaylogo:false,toImageButtonOptions:{format:'svg',filename:data.target+'_'+(data.range_id||'all')+'_'+data.view_id+'_TM_5-95_cluster_violins'}});
 const represented=new Set(data.representatives.filter(c=>visibleCluster(c.cluster)).map(c=>c.cluster));const scored=score.values.filter((value,i)=>Number.isFinite(value)&&represented.has(data.clusters[i])).length;
 $('violinSummary').textContent=scored.toLocaleString()+' scored models in selected structural clusters · '+traces.length+' clusters. Each violin has equal maximum width; labels give cluster sizes. Box shows median and quartiles; density ends at observed min/max. Singleton clusters are individual observations. This is structural similarity, not confidence or a sampling probability.';
 $('violinDownload').hidden=!data.violin_interactive;if(data.violin_interactive)$('violinDownload').href=data.violin_interactive;
 $('violinPdf').hidden=!data.violin_pdf;if(data.violin_pdf)$('violinPdf').href=data.violin_pdf;
}
function showProjection(){if(window.AtlasExplorer)window.AtlasExplorer.feature($('projection').value);}
function pointModelDescriptor(current,index){
 if(!Number.isInteger(index)||index<0||index>=current.models.length)throw Error('Invalid selected model index.');
 if(!Array.isArray(current.model_files)||!Array.isArray(current.model_sha256)||current.model_files.length!==current.models.length||current.model_sha256.length!==current.models.length)throw Error('Exact model files and original hashes are unavailable for this analysis.');
 const file=current.model_files[index],digest=current.model_sha256[index];
 if(typeof file!=='string'||!file||file.startsWith('/')||/[\\:?#]/.test(file)||file.split('/').some(part=>!part||part==='.'||part==='..')||typeof digest!=='string'||!/^[a-f0-9]{64}$/.test(digest))throw Error('Unsafe or unverified exact-model coordinate descriptor.');
 const extension=file.split('.').at(-1).toLowerCase();if(!['cif','mmcif','pdb'].includes(extension))throw Error('Unsupported exact-model coordinate format.');
 const label=current.clusters[index],cluster=current.representatives.find(row=>row.cluster===label),palette=current.schemes.find(s=>s.key==='clusters')?.colors||{};
 return {cluster:label,model:current.models[index],method:current.methods[index],count:current.clusters.filter(value=>value===label).length,color:cluster?.color||palette[label]||'#808080',file,sha256:digest,format:extension==='mmcif'?'cif':extension,exact_model_index:index};
}
async function savedCoordinate(descriptor){
 if(descriptor.coordinate_text)return descriptor.coordinate_text;
 const response=await fetch(descriptor.file,{cache:'no-cache',signal:AbortSignal.timeout(15000)});if(!response.ok)throw Error('HTTP '+response.status);
 let text;
 if(descriptor.sha256&&globalThis.crypto?.subtle){
  const bytes=await response.arrayBuffer(),digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),v=>v.toString(16).padStart(2,'0')).join('');
  if(digest!==descriptor.sha256)throw Error('Original coordinate hash does not match the selected model.');text=new TextDecoder().decode(bytes);
 }else text=await response.text();
 descriptor.coordinate_text=text;return text;
}
async function choose(label,modelIndex=null){
 const current=data,exact=modelIndex!==null,cluster=exact?pointModelDescriptor(current,modelIndex):current.representatives.find(x=>x.cluster===label);
 if(exact&&cluster.cluster!==label)throw Error('The selected point and cluster identity differ.');
 if(structureViewAnchor&&viewer._aisDescriptor)structureViewAnchor.activeCamera=structureCamera();
 const serial=++loadSerial;
 if(!cluster){clearStructure(label+' · no representative',label.endsWith('.unassigned')?'These models were left unassigned by HDBSCAN. Select an individual plotted point to inspect its exact model.':'No saved representative is available for this group.');return}
 selectedModelIndex=exact?modelIndex:null;
 if(exact)$('modelMode').value='medoid';
 const representativeOption=Array.from($('modelMode').options||[]).find(row=>row.value==='medoid');if(representativeOption)representativeOption.textContent=exact?'Selected point model':'Representative';
 configureModelMode(cluster);if(!pairSelecting)$('pairSection').hidden=true;selected=label;$('clusterSelect').value=label;
 if(bonsaiPanel&&current.bonsai)bonsaiPanel.select(label);
 for(const tr of $('clusterRows').children){tr.classList.toggle('selected',tr.dataset.cluster===label);tr.setAttribute('aria-selected',String(tr.dataset.cluster===label))}
 $('error').hidden=true;$('modelTitle').textContent='Loading '+(exact?cluster.model:label)+'…';$('modelInfo').textContent='';$('structure').removeAttribute('href');$('ensemblePdb').hidden=true;$('ensemblePse').hidden=true;
 viewer.spin(false);viewer.removeAllModels();viewer._aisModels=[];viewer._aisDescriptor=null;updateStructureViewControls();viewer.render();
 let coordinate;
 try{coordinate=await savedCoordinate(cluster)}catch(error){if(serial!==loadSerial||data!==current)return;$('modelTitle').textContent=label+' · model unavailable';throw Error('Could not load '+cluster.model+'. '+error.message)}
 if(serial!==loadSerial||data!==current)return;
 if(!exact&&$('modelMode').value==='ensemble'&&!cluster.ensemble_text&&cluster.ensemble_file){const response=await fetch(cluster.ensemble_file);if(!response.ok)throw Error('Ensemble file unavailable');cluster.ensemble_text=await response.text()}
 if(serial!==loadSerial||data!==current)return;
 const ensemble=!exact&&$('modelMode').value==='ensemble'&&cluster.ensemble_text;
 viewer._aisModels=ensemble?viewer.addModels(cluster.ensemble_text,'pdb'):[viewer.addModel(coordinate,cluster.format)];viewer._aisDescriptor=cluster;viewer._aisEnsemble=!!ensemble;
 alignStructureToSetView();styleSavedStructure(viewer,cluster.color,ensemble ? .62 : 1);frameSelectedStructure();viewer.spin(spinning);
 $('modelTitle').textContent=exact?cluster.model+' · exact selected model':label+' · '+(ensemble?(data.ensemble_kind||'comparison ensemble'):(current.representative_kind||'structural representative'));
 $('modelInfo').textContent=`${cluster.model} · ${cluster.method} · ${label} · ${cluster.count.toLocaleString()} ${cluster.count===1?'model':'models'} in cluster (${population(cluster.count)})${Number.isFinite(referenceSimilarity(cluster))?' · TM (5–95): '+referenceSimilarity(cluster).toFixed(3):''}`;
 if(modelDownloadURL)URL.revokeObjectURL(modelDownloadURL);modelDownloadURL=URL.createObjectURL(new Blob([coordinate],{type:'text/plain'}));$('structure').hidden=false;$('structure').href=modelDownloadURL;$('structure').download=cluster.file.split('/').pop();
 if(ensembleDownloadURL)URL.revokeObjectURL(ensembleDownloadURL);$('ensemblePdb').hidden=!cluster.ensemble_file;if(cluster.ensemble_file)$('ensemblePdb').href=cluster.ensemble_file;$('ensemblePse').hidden=!cluster.ensemble_pse;
 if(cluster.ensemble_text){ensembleDownloadURL=URL.createObjectURL(new Blob([cluster.ensemble_text],{type:'text/plain'}));$('ensemblePdb').href=ensembleDownloadURL;$('ensemblePdb').download=cluster.ensemble_file.split('/').pop()}if(cluster.ensemble_pse)$('ensemblePse').href=cluster.ensemble_pse;
 for(const method of ['pca','umap','tsne']){
  const p=current.projections[method].xy,indices=exact?[modelIndex]:current.clusters.map((x,i)=>x===label?i:-1).filter(i=>i>=0),valid=indices.filter(i=>Number.isFinite(p[i][0]));
  const x=valid.reduce((a,i)=>a+p[i][0],0)/valid.length,y=valid.reduce((a,i)=>a+p[i][1],0)/valid.length;
  Plotly.relayout($(method),{annotations:[{x,y,text:exact?cluster.model:label,showarrow:true,arrowhead:2,ax:25,ay:-30,font:{size:11,color:'#153f4d'},bgcolor:'#ffffffdd'}]});
 }
}
function hashSelection(){const [target,query='']=decodeURIComponent(location.hash.slice(1)).split('?'),params=new URLSearchParams(query);return {target,range:params.get('range')||'all',view:params.get('view')||'whole'}}
function analysisHash(target,range,view){const base=encodeURIComponent(target)+'?range='+encodeURIComponent(range||'all')+'&view='+encodeURIComponent(view||'whole');return base+(typeof AISExplorerSelections!=='undefined'?'&'+AISExplorerSelections.routeParams(selectionPreference):'')}
function navigateSavedSection(event){
 const anchor=event.target.closest?.('a[href^="#"]');if(!anchor||event.defaultPrevented||event.button>0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;
 const fragment=anchor.getAttribute('href').slice(1);let id;try{id=decodeURIComponent(fragment)}catch{return}
 const section=$(id);if(!section)return;
 event.preventDefault();if(section.tagName==='DETAILS')section.open=true;section.scrollIntoView({block:'start',behavior:'smooth'});
}
function savedResidueRanges(target){
 const configured=target.residue_ranges||[],entries=configured.filter(r=>typeof r.id==='string'&&typeof r.name==='string'),all=entries.find(r=>r.id==='all');
 return all?entries:[{id:'all',name:'All residues',data:target.data,asset_root:'',default_view:'whole',available:true},...entries];
}
function availableResidueRange(range){return range.available!==false&&typeof range.data==='string'&&!!range.data}
function rangeAssetPath(path,range){
 if(typeof path!=='string'||!path||!range.asset_root||/^(?:[a-z]+:|\/)/i.test(path))return path;
 const root=range.asset_root.replace(/\/?$/,'/');return path.startsWith(root)?path:root+path.replace(/^\.\//,'');
}
function prepareRangeAnalysis(raw,range){
 // Rebase only file references. Scientific arrays, coordinates, labels and scores stay exact.
 const current={...raw,range_id:range.id,range_name:range.name};
 current.views=(raw.views||[]).map(view=>({...view,data:rangeAssetPath(view.data,range)}));
 if(Array.isArray(raw.model_files))current.model_files=raw.model_files.map(path=>rangeAssetPath(path,range));
 current.representatives=raw.representatives.map(row=>{const out={...row};for(const key of ['file','ensemble_file','ensemble_pse'])if(out[key])out[key]=rangeAssetPath(out[key],range);return out});
 current.heatmaps=(raw.heatmaps||[]).map(row=>({...row,file:rangeAssetPath(row.file,range)}));
 if(raw.bonsai)current.bonsai={...raw.bonsai,file:rangeAssetPath(raw.bonsai.file,range)};
 if(raw.medoid_tm)current.medoid_tm={...raw.medoid_tm,csv:rangeAssetPath(raw.medoid_tm.csv,range)};
 for(const key of ['membership_file','violin_interactive','violin_pdf'])if(raw[key])current[key]=rangeAssetPath(raw[key],range);
 return current;
}
async function savedViewSelection(target,range,requested){
 // A curated catalog is resolved before fetching: retired URLs never load a hidden analysis.
 if(Array.isArray(range.views)){
  const views=range.views.filter(view=>['primary','density'].includes(view.id));
  const available=view=>view?.available!==false&&typeof view?.data==='string'&&!!view.data;
  const primary=views.find(view=>view.id==='primary'&&available(view));
  if(!primary)throw Error('The curated range has no verified Primary analysis.');
  const view=views.find(view=>view.id===requested&&available(view))||primary;
  async function read(binding){
   const raw=await json(binding.data);
   if(raw.target!==target.id||raw.view_id!==binding.source_view_id)throw Error('Saved analysis differs from the verified view catalog.');
   const current=prepareRangeAnalysis(raw,{...range,asset_root:binding.asset_root||''});
   return {...current,views,policy_view_id:binding.id,visible_view_policy:true,
    presentation_asset_root:binding.asset_root||'',view_title:raw.target+' · '+binding.name+' · '+range.name};
  }
  const base=await read(primary),loaded=view===primary?base:await read(view);
  return {base,loaded,view};
 }
 const rawBase=await json(range.data),base=prepareRangeAnalysis(rawBase,range),views=base.views||[],view=views.find(x=>x.id===requested)||views.find(x=>x.id===(range.default_view||'whole'));
 return {base,loaded:view&&view.id!=='whole'?prepareRangeAnalysis(await json(view.data),range):base,view};
}
function configureResidueRangeControls(target,selectedRange,requested){
 const select=$('residueRange');select.replaceChildren(...savedResidueRanges(target).map(range=>Object.assign(document.createElement('option'),{value:range.id,textContent:range.name+(availableResidueRange(range)?'':' — '+(range.status||'awaiting verified results')),disabled:!availableResidueRange(range)})));select.value=selectedRange.id;
 const unavailable=requested!==selectedRange.id,note=$('residueRangeNote');note.hidden=!unavailable;note.textContent=unavailable?'The requested residue-range analysis is unavailable. Showing '+selectedRange.name+'; no regional result is substituted.':'';
}

function setAnalysisLoading(loading){
 selectionLoading=loading;updateSelectionControls();
 $('clusterExplorer').setAttribute('aria-busy',String(loading));
 for(const id of ['residueRange','analysisView','color','clear','family','clusterSubset','allClusters','clusterSelect','modelMode','structureScope','structureColor','setStructureView'])$(id).disabled=loading;
 if(!loading)updateStructureViewControls();
}
function clearStructure(title='Select a cluster',note=''){
 if(structureViewAnchor&&viewer._aisDescriptor)structureViewAnchor.activeCamera=structureCamera();
 ++loadSerial;++pairSerial;selected=null;selectedModelIndex=null;viewer._aisDescriptor=null;viewer._aisModels=[];$('clusterSelect').value='';viewer.spin(false);viewer.removeAllModels();viewer._aisModels=[];viewer._aisDescriptor=null;viewer.render();
 $('modelTitle').textContent=title;$('modelInfo').textContent=note;
 for(const id of ['structure','ensemblePdb','ensemblePse']){$(id).removeAttribute('href');$(id).hidden=true}
 $('pairSection').hidden=true;if(bonsaiPanel)bonsaiPanel.select(null);
 updateStructureViewControls();
 for(const tr of $('clusterRows').children){tr.classList.remove('selected');tr.setAttribute('aria-selected','false')}
}
async function load(target,viewId='whole',rangeId='all'){
 const request=++targetRequest;++loadSerial;++pairSerial;clearSamplingHighlight();setAnalysisLoading(true);try{
 if(structureViewAnchor&&viewer._aisDescriptor)structureViewAnchor.activeCamera=structureCamera();
 $('modelTitle').textContent='Loading analysis…';$('modelInfo').textContent='';$('structure').removeAttribute('href');$('ensemblePdb').hidden=true;$('ensemblePse').hidden=true;viewer.spin(false);viewer.removeAllModels();viewer._aisModels=[];viewer._aisDescriptor=null;viewer.render();
 const found=atlas.targets.find(x=>x.id===target)||atlas.targets[0],ranges=savedResidueRanges(found),range=ranges.find(r=>r.id===rangeId&&availableResidueRange(r))||ranges.find(r=>r.id==='all'&&availableResidueRange(r));
 if(!range)throw Error('No verified residue-range analysis is available for this target.');
 const {base,loaded,view}=await savedViewSelection(found,range,viewId);if(request!==targetRequest)return;const [enriched,highlightResult]=await Promise.all([metricOverlayLoader?metricOverlayLoader.enrich(loaded):withoutUnavailableRefolds(loaded),selectionLoader?selectionLoader.load(loaded):{status:'unavailable',payload:null,note:'No saved selection highlights are available for this analysis.'}]);if(request!==targetRequest)return;return await (renderQueue=renderQueue.catch(()=>{}).then(async()=>{if(request!==targetRequest)return;data=enriched;selectionResult=highlightResult;selectionPayload=highlightResult.payload;selected=null;selectedModelIndex=null;if(data.visible_view_policy&&(view.id!==viewId||range.id!==rangeId||found.id!==target))window.history?.replaceState(null,'','#'+analysisHash(found.id,range.id,view.id));configureResidueRangeControls(found,range,rangeId);configureRefinementControls();configureStructureControls();configureModelMode();window.dispatchEvent(new CustomEvent('atlas:cohort',{detail:{current:data,base,range}}));
 const previousColor=$('color').value,requestedColor=new URLSearchParams(location.search).get('color');
 $('analysisViewLabel').hidden=false;$('analysisView').replaceChildren(...(base.views||[]).map(x=>Object.assign(document.createElement('option'),{value:x.id,textContent:x.name+(x.available===false?' — '+(x.status||'awaiting verified results'):''),disabled:x.available===false})));$('analysisView').value=view?.id||'whole';
 $('title').textContent=data.view_title||data.target;$('summary').textContent=`${range.name} · ${data.models.length.toLocaleString()} models · ${new Set(data.methods).size} methods · ${data.representatives.length} structural clusters · ${data.clusters.filter(x=>x.endsWith(".unassigned")).length.toLocaleString()} unassigned · ${data.residues} residues in supplied construct`;
 $('representativePolicy').textContent=data.representative_policy||'One exact structural medoid per cluster, selected by mean pairwise rigid-fit Cα RMSD. Medoids are structural representatives, independently of confidence.';
 $('clusterMethod').textContent=data.clustering_method_note||'All projections use the same retained, sequence-aligned Cα distance features and the default terminal-variance mask. Clusters preserve disconnected components of the seed-42 UMAP 15-neighbor graph; candidate subdivisions require feature silhouette ≥ 0.15 and agreement ≥ 0.80 with seeds 7 and 123. Cluster colors identify the same memberships in every projection.';
 $('metricNote').hidden=!data.metric_note;$('metricNote').textContent=data.metric_note||'';$('tmColumn').hidden=!data.metric_note;
 updateStructureViewControls();
 for(const a of $('targets').children)a.setAttribute('aria-current',a.dataset.target===data.target?'page':'false');
 const visibleSchemes=typeof AISExplorerMetrics!=='undefined'?AISExplorerMetrics.populateSelect($('color'),data.schemes):data.schemes.filter(s=>s.key!=='origin');if(typeof AISExplorerMetrics==='undefined')$('color').replaceChildren(...visibleSchemes.map(s=>Object.assign(document.createElement('option'),{value:s.key,textContent:s.name+(s.unavailable?' — unavailable':''),disabled:!!s.unavailable})));$('colorAvailability').textContent=visibleSchemes.some(s=>s.unavailable)?'Some saved score observations are unavailable for this cohort; no values are imputed.':'';
 $('color').value=visibleSchemes.find(s=>s.key==='clusters'&&!s.unavailable)?.key||visibleSchemes.find(s=>!s.unavailable).key;
 const preferredColor=previousColor||requestedColor;if(visibleSchemes.some(s=>s.key===preferredColor&&!s.unavailable))$('color').value=preferredColor;updateMetricOverlayNote();refreshSelectionHighlight();
 const reviewDownloads=data.review_downloads||(range.id==='all'&&!data.visible_view_policy?{waveMemberships:'wave-memberships.csv',decisionsDownload:'decisions.csv',boundsDownload:'bounds.json'}:{});for(const id of ['waveMemberships','decisionsDownload','boundsDownload']){const path=reviewDownloads[id];$(id).hidden=!path;if(path)$(id).href=rangeAssetPath(path,{...range,asset_root:data.presentation_asset_root??range.asset_root});else $(id).removeAttribute('href')}
 $('members').href=data.membership_file;$('clusterRows').replaceChildren();$('clusterSelect').replaceChildren(Object.assign(document.createElement('option'),{value:'',textContent:'Select a cluster'}),...data.representatives.map(c=>Object.assign(document.createElement('option'),{value:c.cluster,textContent:c.cluster+' · '+c.count.toLocaleString()})));
 for(const c of data.representatives){const tr=document.createElement('tr');tr.dataset.cluster=c.cluster;tr.tabIndex=0;tr.setAttribute('role','button');tr.setAttribute('aria-label','Inspect '+c.cluster);tr.innerHTML=`<td><span class="dot" style="background:${c.color}"></span>${escapeText(c.cluster)}</td><td>${c.count.toLocaleString()}</td><td>${escapeText(population(c.count))}</td><td>${escapeText(c.method)}</td>${data.metric_note?'<td>'+(Number.isFinite(referenceSimilarity(c))?referenceSimilarity(c).toFixed(3):'Unavailable')+'</td>':''}<td>${c.ensemble_file?'<a download href="'+escapeText(c.ensemble_file)+'">PDB</a>':''} ${c.ensemble_pse?'<a download href="'+escapeText(c.ensemble_pse)+'">PSE</a>':''}</td>`;for(const a of tr.querySelectorAll('a')){a.onclick=e=>e.stopPropagation();a.onkeydown=e=>e.stopPropagation()}tr.onclick=()=>choose(c.cluster).catch(fail);tr.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();choose(c.cluster).catch(fail)}};$('clusterRows').append(tr)}
 configureDistanceMaps();
 $('mask').textContent=data.mask_note;$('provenance').textContent=JSON.stringify(data.provenance,null,2);
 await draw();if(request===targetRequest){if(data.representatives.length)await choose(data.representatives[0].cluster);if(request===targetRequest)setAnalysisLoading(false)}
 }));
 }catch(error){if(request===targetRequest)throw error}
}
async function start(){
 document.addEventListener('click',navigateSavedSection);
 const loaded=await Promise.all([json('atlas.json'),fetchClusteringResidues(),fetchOptionalJSON('residue-ranges.json'),fetchOptionalJSON('projection-metadata.json'),fetchOptionalJSON('supplementary-metadata.json'),fetchOptionalJSON('metric-overlays.json'),fetchOptionalJSON('selection-highlights.json')]);metricOverlayLoader=typeof AISExplorerMetrics!=='undefined'?AISExplorerMetrics.createLoader(loaded[5]):null;selectionLoader=typeof AISExplorerSelections!=='undefined'?AISExplorerSelections.createLoader(loaded[6]):null;atlas=loaded[0];clusteringResidueCatalog=loaded[1];projectionMetadataCatalog=loaded[3];supplementaryMetadataCatalog=loaded[4];const rangeCatalog=loaded[2];atlas={...atlas,targets:atlas.targets.map(target=>({...target,residue_ranges:rangeCatalog.targets?.[target.id]?.residue_ranges||target.residue_ranges}))};for(const t of atlas.targets){const a=document.createElement('a');a.href='#'+encodeURIComponent(t.id);a.textContent=t.id;a.dataset.target=t.id;$('targets').append(a)}
 viewer=$3Dmol.createViewer($('molecule'),{backgroundColor:'white',antialias:true});$('clusterSelect').onchange=()=>{if($('clusterSelect').value)choose($('clusterSelect').value).catch(fail)};
 $('structureScope').onchange=()=>{structureScopePreference=$('structureScope').value;restyleStructureViews()};$('structureColor').onchange=restyleStructureViews;
 $('modelMode').onchange=()=>{if(selected)choose(selected,$('modelMode').value==='ensemble'?null:selectedModelIndex).catch(fail)};$('color').onchange=()=>{updateMetricOverlayNote();scheduleDraw().catch(fail)};$('projection').onchange=showProjection;$('clear').onclick=()=>{clearStructure();for(const m of ['pca','umap','tsne'])Plotly.relayout($(m),{annotations:[],'xaxis.autorange':true,'yaxis.autorange':true})};
 for(const id of ['selectionMethod','selectionBalance','selectionPressure','selectionReplicate'])if($(id))$(id).onchange=changeSavedSelection;
 $('analysisView').onchange=()=>{location.hash=analysisHash(data.target,$('residueRange').value,$('analysisView').value)};
 $('residueRange').onchange=()=>{location.hash=analysisHash(data.target,$('residueRange').value,$('analysisView').value)};
 $('setStructureView').onclick=setStructureView;
 $('reset').onclick=()=>frameSelectedStructure(structureViewAnchor?.camera);$('spin').onclick=()=>{spinning=!spinning;viewer.spin(spinning);$('spin').setAttribute('aria-pressed',String(spinning));$('spin').textContent=spinning?'Stop rotation':'Rotate'};
 window.addEventListener('hashchange',()=>{const s=hashSelection();readSelectionRoute();if(atlas.targets.some(t=>t.id===s.target)){if(data?.target===s.target&&(data.range_id||'all')===s.range&&(data.policy_view_id||data.view_id)===s.view){refreshSelectionHighlight();scheduleSelectionDraw().catch(fail)}else load(s.target,s.view,s.range).catch(fail)}});window.addEventListener('resize',()=>viewer.resize());window.addEventListener('atlas:layout',()=>{viewer.resize();pairViewers.forEach(v=>v.resize())});const s=hashSelection();readSelectionRoute();await load(s.target,s.view,s.range);
}
window.addEventListener('DOMContentLoaded',()=>start().catch(fail));

async function drawCandidateReview(){
 const review=data.visible_view_policy?null:data.count_review;$('countReview').hidden=!review;if(!review)return;
 $('countNote').textContent=review.note;
 const rows=review.counts,common={paper_bgcolor:'#fff',plot_bgcolor:'#fff',margin:{l:70,r:25,t:30,b:50},font:{family:'Arial, sans-serif',size:12,color:'#344f5b'}};
 const lines=[['within_tm_equal_cluster','Within-cluster TM','#196a8b'],['between_tm_equal_cluster_pair','Between-cluster TM','#ce6818'],['provisional_tm_contrast','Within minus between','#7c5197']].map(([key,name,color])=>({type:'scatter',mode:'lines+markers',name,x:rows.map(r=>r.k),y:rows.map(r=>r[key]),line:{color,width:2},marker:{size:6},hovertemplate:'K=%{x}<br>%{y:.4f}<extra>'+name+'</extra>'}));
 await AtlasResponsive.react($('countTradeoff'),lines,{...common,xaxis:{title:{text:'Candidate child-cluster count K'},dtick:1},yaxis:{title:{text:'TM similarity / contrast'},range:[Math.min(0,...rows.map(r=>r.provisional_tm_contrast??0))-.03,1]},legend:{orientation:'h',y:1.18},annotations:data.candidate_k?[{x:data.candidate_k,y:0,yref:'paper',text:'Current K='+data.candidate_k,showarrow:true,ay:-30}]:[]},{responsive:true,displaylogo:false});
 const current=rows.find(r=>r.k===data.candidate_k);$('ensembleTM').hidden=!current;if(!current)return;
 const matrix=Array.from({length:current.k},()=>Array(current.k).fill(null));for(const c of current.clusters)matrix[c.cluster-1][c.cluster-1]=c.within_tm;for(const p of current.between_cluster_pairs)matrix[p.left-1][p.right-1]=matrix[p.right-1][p.left-1]=p.mean_tm;
 const recordedLabels=current.labels||[...new Set(data.clusters)].filter(label=>!label.endsWith('.unassigned'));const labels=recordedLabels.length===current.k?recordedLabels:Array.from({length:current.k},(_,i)=>'Cluster '+(i+1));
 await AtlasResponsive.react($('ensembleTM'),[{type:'heatmap',z:matrix,x:labels,y:labels,zmin:0,zmax:1,colorscale:'Plasma',text:matrix.map(row=>row.map(v=>v===null?'':v.toFixed(2))),texttemplate:current.k<=15?'%{text}':'',textfont:{size:11},colorbar:{title:{text:'TM similarity'}},hovertemplate:'%{y} / %{x}<br>Mean ensemble TM: %{z:.4f}<extra></extra>'}],{...common,title:{text:'K='+current.k+' representative-ensemble TM'},yaxis:{autorange:'reversed'},xaxis:{tickangle:-45}},{responsive:true,displaylogo:false});
 $('tmEstimateNote').textContent='Off diagonal: population-weighted mean TM between each pair of representative ensembles. Diagonal: within-ensemble mean, excluding self pairs; unavailable estimates are blank. All K reuse one fixed, distance-stratified pool. These are representative estimates, not all-model distributions. Final K remains unselected.';
}

async function drawMedoidTM(){
 const grid=filteredMedoidGrid();$('medoidTMTitle').textContent=grid?.title||'TM similarity across cluster medoids';$('medoidTM').hidden=!grid;$('medoidTMNote').textContent=grid?.note||data.medoid_tm_note||'The complete medoid matrix is being prepared; no truncated grid is substituted.';$('medoidTMCsv').hidden=!grid?.csv;if(!grid)return;
 if(grid.csv)$('medoidTMCsv').href=grid.csv;
 const n=grid.labels.length,height=Math.max(500,Math.min(1000,250+n*18));
 // Reserve the rendered plot height in document flow, including after subset changes.
 $('medoidTM').style.height=height+'px';
 await AtlasResponsive.react($('medoidTM'),[{type:'heatmap',z:grid.matrix,x:grid.labels,y:grid.labels,zmin:0,zmax:1,colorscale:'Plasma',text:grid.matrix.map(row=>row.map(v=>Number.isFinite(v)?v.toFixed(2):'')),texttemplate:n<=15?'%{text}':'',colorbar:{title:{text:'TM similarity'}},hovertemplate:'%{y} / %{x}<br>TM: %{z:.4f}<extra></extra>'}],{paper_bgcolor:'#fff',margin:{l:85,r:30,t:20,b:100},font:{family:'Arial, sans-serif',size:11,color:'#344f5b'},xaxis:{tickangle:-55},yaxis:{autorange:'reversed',scaleanchor:'x'},height},{responsive:true,displaylogo:false,toImageButtonOptions:{format:'svg',filename:data.target+'_'+(data.range_id||'all')+'_'+data.view_id+'_medoid_TM'}});
 $('medoidTM').removeAllListeners('plotly_click');$('medoidTM').on('plotly_click',e=>{const point=e.points[0];if(Number.isFinite(point.z))chooseMedoidPair(point.y,point.x,point.z).catch(fail)});
}

let bonsaiPanel=null,bonsaiSerial=0;
async function drawBonsai(){
 const serial=++bonsaiSerial,current=data;$('bonsaiPanel').hidden=!current.bonsai;if($('bonsaiDetails'))$('bonsaiDetails').hidden=!current.bonsai;if(!current.bonsai)return;
 if(!current.bonsaiPayload){const response=await fetch(current.bonsai.file,{cache:'no-cache'});if(!response.ok)throw Error('Saved Bonsai layout unavailable');const bytes=await response.arrayBuffer(),digest=globalThis.crypto?.subtle?Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(x=>x.toString(16).padStart(2,'0')).join(''):null;if(digest!==null&&digest!==current.bonsai.sha256)throw Error('Saved Bonsai layout hash mismatch');current.bonsaiPayload=JSON.parse(new TextDecoder().decode(bytes));}
 if(serial!==bonsaiSerial||data!==current)return;
 if(!bonsaiPanel)bonsaiPanel=BonsaiEnsemble.create($('bonsai'),{onChoose:(cluster,model)=>choose(cluster).catch(fail),detailsHref:'#bonsaiDetails'});
 const representatives=current.representatives.filter(c=>visibleCluster(c.cluster));
 if($('bonsaiStructureDetails'))$('bonsaiStructureDetails').textContent=representatives.some(row=>row.ensemble_file||row.ensemble_text)?'Use Structure view to switch between Representative and Comparison ensemble.':'The 3D viewer shows the saved cluster representative; coordinate ensembles are unavailable for this result.';
 const models=current.bonsaiPayload.models.filter(r=>visibleCluster(current.clusters[current.models.indexOf(r.model)])),key=models.map(r=>r.model).join('\0');if(current.filteredBonsai?.key!==key)current.filteredBonsai={key,payload:{...current.bonsaiPayload,models}};const filtered=current.filteredBonsai.payload;bonsaiPanel.update({...current,representatives},filtered,scheme(),$('pca'),hiddenProjectionCategories,selectionHighlight.active?new Set(selectionHighlight.orderedIndices.map(i=>current.models[i])):null);if(selected)bonsaiPanel.select(selected);
}

window.AtlasPlotActions={async reset(method){if(method==='bonsai')bonsaiPanel?.resetView();else await AtlasResponsive.reset($(method))},async save(method){if(method==='bonsai')return bonsaiPanel?.savePNG();return Plotly.downloadImage($(method),{format:'png',filename:data.target+'_'+(data.range_id||'all')+'_'+method,width:1200,height:900})}};
