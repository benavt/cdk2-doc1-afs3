/* Optional, hash-bound saved model metrics. Never fit, rank or alter an analysis. */
(function(root){'use strict';
const RETIRED=new Set(['boltz2_exact_refold_ptm','boltz2_exact_refold_mean_plddt','boltz2_exact_refold_template_tm']);
const SCOPE_NOTE='ProteinEBM model 6 energy uses the full saved construct and is reused across clustering procedures and residue-range views; it was not recomputed for the selected clustering mask. Arbitrary units; lower is better. Scores are not calibrated across targets. The saved default t=0.10 is a conditioning/noise level, not a trajectory time.';
function need(value,message){if(!value)throw Error(message);}
function hash(value){return typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);}
function equal(a,b){if(a===b)return true;if(!a||!b||typeof a!=='object'||typeof b!=='object'||Array.isArray(a)!==Array.isArray(b))return false;const ak=Object.keys(a).sort(),bk=Object.keys(b).sort();return ak.length===bk.length&&ak.every((k,i)=>k===bk[i]&&equal(a[k],b[k]));}
function cleanSchemes(data){
 return data.schemes.filter(s=>{
  if(!RETIRED.has(s.key))return true;
  need(s.unavailable===true&&Array.isArray(s.values)&&s.values.length===data.models.length&&s.values.every(v=>v===null),'A populated refold observation cannot be replaced by a metric overlay.');
  return false;
 });
}
function descriptor(s){
 need(s&&s.key==='protein_ebm_energy_t10'&&s.type==='continuous','Invalid saved energy scheme identity.');
 need(s.time_index===10&&typeof s.time_value==='number'&&Math.abs(s.time_value-.1)<1e-12,'Invalid saved energy conditioning level.');
 need(s.colorscale==='Viridis'&&s.lower_is_better===true&&s.model_version===6&&s.units==='arbitrary'&&s.primary===true,'Unsupported saved energy interpretation.');
 need(Array.isArray(s.range)&&s.range.length===2&&s.range.every(Number.isFinite)&&s.range[0]<=s.range[1],'Invalid saved energy color range.');
}
function targetIdentity(entry,payload,data){
 need(payload&&payload.schema_version===1&&payload.target===data.target,'Saved energy target differs from this analysis.');
 need(Number.isInteger(entry.model_count)&&entry.model_count>0&&entry.model_count===data.models.length&&Array.isArray(payload.models)&&payload.models.length===data.models.length&&payload.models.every((n,i)=>typeof n==='string'&&n===data.models[i]),'Saved energy model order differs from this analysis.');
 for(const key of ['model_order_sha256','sequence_sha256','source_dataset_sha256'])need(hash(entry[key])&&entry[key]===payload[key],'Saved energy identity hash differs: '+key);
 const parent=data.provenance?.original_parent_provenance||data.provenance||{};
 need(parent.sequence_sha256===entry.sequence_sha256,'Saved energy sequence differs from this analysis.');
 need(entry.energy_scope==='full_construct'&&payload.energy_scope==='full_construct'&&equal(entry.scoring_residues,payload.scoring_residues),'Saved energy scope differs.');
 const count=Array.isArray(entry.scoring_residues)?entry.scoring_residues.length:entry.scoring_residues;
 need(count===data.residues,'Saved energy does not cover this full construct.');
 if(Array.isArray(entry.scoring_residues))need(entry.scoring_residues.every((n,i)=>n===i+1),'Saved energy scope must use canonical full-construct residues.');
 need(Array.isArray(entry.schemes)&&entry.schemes.length===1&&Array.isArray(payload.schemes)&&payload.schemes.length===1,'Only the one saved default energy level at t=0.10 is supported.');
 const declared=entry.schemes[0],saved=payload.schemes[0];descriptor(declared);descriptor(saved);
 need(!Object.hasOwn(declared,'values'),'The metric catalog must not contain model values.');
 const {values,...metadata}=saved;need(equal(metadata,declared),'Saved energy descriptor differs from its catalog.');
 need(Array.isArray(values)&&values.length===data.models.length&&values.every(v=>typeof v==='number'&&Number.isFinite(v)),'Invalid or incomplete saved energy values.');
 need(Math.min(...values)===saved.range[0]&&Math.max(...values)===saved.range[1],'Saved energy bounds differ from full-cohort values.');
 return [{...saved,values:[...values],name:'ProteinEBM energy · t=0.10',short_name:'Energy · t=0.10',metric_note:SCOPE_NOTE,metric_scope_count:count}];
}
async function readPayload(file,expected){
 const response=await root.fetch(file,{cache:'no-cache',signal:AbortSignal.timeout(30000)});
 need(response.ok,'Saved energy payload is unavailable.');const bytes=await response.arrayBuffer();
 // Private HTTP may lack SubtleCrypto. The verified serving manifest checks file
 // bytes; exact ordered models, sequence and view bindings remain mandatory here.
 if(root.crypto?.subtle){const digest=Array.from(new Uint8Array(await root.crypto.subtle.digest('SHA-256',bytes)),v=>v.toString(16).padStart(2,'0')).join('');need(digest===expected,'Saved energy payload hash differs.');}
 return JSON.parse(new TextDecoder().decode(bytes));
}
function createLoader(catalog,reader=readPayload){
 const cache=new Map();
 return {async enrich(data){
  const schemes=cleanSchemes(data),clean={...data,schemes};
  const entry=catalog?.schema_version===1?catalog.targets?.[data.target]:null;
  if(!entry)return clean;
  try{
   need(typeof entry.file==='string'&&entry.file==='metrics/'+data.target+'.json'&&/^metrics\/[A-Za-z0-9_-]+\.json$/.test(entry.file)&&hash(entry.sha256),'Unsafe or unhashed saved energy payload.');
   const range=data.range_id||'all',view=data.view_id||'whole',bound=entry.ranges?.[range]?.views?.[view];
   const policy=data.views?.find(row=>row.id===data.policy_view_id);
   need(data.visible_view_policy===true&&policy?.source_view_id===view&&hash(policy.source_data_sha256)&&bound?.source_data_sha256===policy.source_data_sha256,'Saved energy binding differs from the verified analysis.');
   const key=entry.file+'|'+entry.sha256;
   if(!cache.has(key))cache.set(key,Promise.resolve().then(()=>reader(entry.file,entry.sha256)));
   const payload=await cache.get(key),added=targetIdentity(entry,payload,data);
   need(!added.some(s=>schemes.some(old=>old.key===s.key)),'Saved energy scheme key collides with existing observations.');
   return {...clean,schemes:[...schemes,...added],metric_overlay_status:'available',metric_overlay_note:SCOPE_NOTE};
  }catch(error){return {...clean,metric_overlay_status:'unavailable',metric_overlay_note:'ProteinEBM energy is unavailable for this analysis: '+error.message};}
 }};
}
function populateSelect(select,schemes){
 const visible=schemes.filter(s=>s.key!=='origin');
 const options=visible.map(scheme=>{const option=document.createElement('option');option.value=scheme.key;option.textContent=scheme.name+(scheme.unavailable?' — unavailable':'');option.disabled=!!scheme.unavailable;return option;});
 select.replaceChildren(...options);return visible;
}
function note(data,key){const s=data.schemes.find(s=>s.key===key);return s?.metric_note?'ProteinEBM · t='+s.time_value.toFixed(2)+' · full construct ('+s.metric_scope_count+' residues) · arbitrary units · lower is better.':data.metric_overlay_status==='unavailable'?data.metric_overlay_note:'';}
const api={createLoader,populateSelect,note,cleanSchemes,targetIdentity,RETIRED,SCOPE_NOTE};root.AISExplorerMetrics=api;
if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
