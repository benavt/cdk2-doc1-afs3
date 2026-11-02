/* Optional saved finite-pool selections. This module never samples or scores. */
(function(root){'use strict';
const METHODS=['none','uniform','panel','exact','mh','disco'];
const DEFAULTS={method:'panel',alpha:.5,tau_multiplier:1,replicate:1};
const ALPHAS=[0,.5,1],PRESSURES=[.5,1,2];
function need(value,message){if(!value)throw Error(message);}
function hash(v){return typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);}
function indices(values,n,count=null){
 need(Array.isArray(values)&&(count===null||values.length===count)&&values.every(i=>Number.isInteger(i)&&i>=0&&i<n)&&new Set(values).size===values.length,'Saved selection indices are invalid, repeated or outside the cohort.');
}
function panels(rows,n){need(Array.isArray(rows)&&rows.length===20,'Twenty saved panel replicates are required.');for(const row of rows)indices(row,n,200);}
function binding(data){const view=data.view_id||'whole',policy=data.views?.find(row=>row.id===data.policy_view_id);need(data.visible_view_policy===true&&policy?.source_view_id===view&&hash(policy.source_data_sha256),'Selection highlights require a verified saved-analysis binding.');return policy.source_data_sha256;}
function validatePayload(payload,entry,targetEntry,data){
 const n=data.models.length,source=binding(data);
 need(payload?.schema_version===1&&payload.target===data.target&&payload.range_id===(data.range_id||'all')&&payload.view_id===(data.view_id||'whole'),'Saved selection target/range/procedure differs from this analysis.');
 need(targetEntry.model_count===n&&entry.model_count===n&&hash(targetEntry.model_order_sha256)&&entry.model_order_sha256===targetEntry.model_order_sha256&&payload.model_order_sha256===entry.model_order_sha256,'Saved selection cohort identity differs.');
 need(hash(entry.source_data_sha256)&&entry.source_data_sha256===source&&payload.source_data_sha256===source,'Saved selection source-view hash differs.');
 need(Array.isArray(payload.models)&&payload.models.length===n&&payload.models.every((name,i)=>typeof name==='string'&&name===data.models[i]),'Saved selection model order differs.');
 need(hash(payload.run?.plan_sha256)&&/^[a-f0-9]{40}$/.test(payload.run?.source_commit||'')&&payload.run.conditioning_t===.1,'Saved selection run provenance is incomplete or uses another conditioning level.');
 panels(payload.uniform_panels,n);
 need(payload.disco&&Number.isInteger(payload.disco.draws)&&payload.disco.draws>=0,'Saved per-cluster control is invalid.');indices(payload.disco.indices,n,payload.disco.draws);
 const structural=new Set(data.representatives.map(row=>row.cluster));
 need(payload.disco.indices.length===structural.size&&new Set(payload.disco.indices.map(i=>data.clusters[i])).size===structural.size&&payload.disco.indices.every(i=>structural.has(data.clusters[i])),'The saved per-cluster control does not match structural clusters.');
 need(Array.isArray(payload.conditions)&&payload.conditions.length===9,'Nine saved balance/pressure conditions are required.');
 const keys=new Set(),ids=new Set();let iqr=null;
 for(const row of payload.conditions){
  need(typeof row.id==='string'&&/^condition-\d{3}$/.test(row.id)&&!ids.has(row.id),'Saved selection condition identity is invalid or repeated.');ids.add(row.id);
  need(ALPHAS.includes(row.alpha)&&PRESSURES.includes(row.tau_multiplier)&&Number.isFinite(row.tau)&&row.tau>0&&Number.isFinite(row.energy_iqr)&&row.energy_iqr>0,'Saved balance or selection pressure is invalid.');
  need(Math.abs(row.tau-row.energy_iqr*row.tau_multiplier)<=1e-10*Math.max(1,row.tau),'Saved selection pressure does not match its energy IQR.');
  need(iqr===null||iqr===row.energy_iqr,'Saved conditions must use one fixed energy IQR.');iqr=row.energy_iqr;
  const key=row.alpha+'|'+row.tau_multiplier;need(!keys.has(key),'Repeated saved balance/pressure condition.');keys.add(key);
  panels(row.panels,n);
  for(const [name,draws]of [['exact',40000],['mh',36000]]){need(row[name]?.draws===draws,'Saved visited-model draw count differs.');indices(row[name].indices,n);need(row[name].indices.length>0&&row[name].indices.length<=draws,'Saved visited-model set is empty or exceeds its draw count.');}
  if(Object.hasOwn(row,'diagnostics')){const d=row.diagnostics;need(d&&Object.keys(d).length===3&&['mh_cluster_total_variation','matched_iid_cluster_total_variation'].every(k=>typeof d[k]==='number'&&Number.isFinite(d[k])&&d[k]>=0&&d[k]<=1)&&Number.isInteger(d.unvisited_assigned_clusters)&&d.unvisited_assigned_clusters>=0&&d.unvisited_assigned_clusters<=structural.size,'Saved selection diagnostics are invalid.');const visited=new Set(row.mh.indices.map(i=>data.clusters[i]));need(d.unvisited_assigned_clusters===[...structural].filter(c=>!visited.has(c)).length,'Saved unvisited-cluster diagnostics differ from memberships.');}
 }
 return payload;
}
async function readPayload(file,expected){
 const response=await root.fetch(file,{cache:'no-cache',signal:AbortSignal.timeout(30000)});need(response.ok,'Saved selection payload is unavailable.');const bytes=await response.arrayBuffer();
 // Private HTTP may lack WebCrypto. The verified server manifest binds bytes;
 // exact ordered models and the source-view binding are mandatory either way.
 if(root.crypto?.subtle){const sha=Array.from(new Uint8Array(await root.crypto.subtle.digest('SHA-256',bytes)),v=>v.toString(16).padStart(2,'0')).join('');need(sha===expected,'Saved selection payload hash differs.');}
 return JSON.parse(new TextDecoder().decode(bytes));
}
function createLoader(catalog,reader=readPayload){
 const cache=new Map();
 return {enabled:catalog?.schema_version===1&&!!catalog.targets&&Object.keys(catalog.targets).length>0,async load(data){
  const target=catalog?.schema_version===1?catalog.targets?.[data.target]:null;
  const entry=target?.ranges?.[data.range_id||'all']?.views?.[data.view_id||'whole'];
  if(!entry)return {status:'unavailable',payload:null,note:'No completed selection results are available for this target, residue range and clustering procedure.'};
  try{
   need(typeof entry.file==='string'&&/^selection-highlights\/[a-z0-9]+(?:-[a-z0-9]+)*\.json$/.test(entry.file)&&hash(entry.sha256),'Unsafe or unhashed saved selection payload.');
   need(entry.source_data_sha256===binding(data),'Saved selection binding differs from the verified analysis.');
   const key=entry.file+'|'+entry.sha256;
   if(!cache.has(key))cache.set(key,Promise.resolve().then(()=>reader(entry.file,entry.sha256)));
   const payload=await cache.get(key);validatePayload(payload,entry,target,data);
   return {status:'available',payload,note:''};
  }catch(error){return {status:'unavailable',payload:null,note:'Saved selection highlights are unavailable: '+error.message};}
 }};
}
function settings(value={}){
 const out={...DEFAULTS,...value};
 need(METHODS.includes(out.method)&&ALPHAS.includes(out.alpha)&&PRESSURES.includes(out.tau_multiplier)&&Number.isInteger(out.replicate)&&out.replicate>=1&&out.replicate<=20&&!out.invalid,'Invalid saved selection settings.');return out;
}
function parseSettings(params,previous=DEFAULTS){
 const out={...DEFAULTS,...previous,invalid:false};
 for(const [key,field]of [['selection','method'],['balance','alpha'],['pressure','tau_multiplier'],['replicate','replicate']])if(params.has(key))out[field]=field==='method'?params.get(key):Number(params.get(key));
 try{return settings(out)}catch{return {...DEFAULTS,...previous,method:'none',invalid:true}}
}
function routeParams(value){const s=settings({...value,invalid:false});return new URLSearchParams({selection:s.method,balance:String(s.alpha),pressure:String(s.tau_multiplier),replicate:String(s.replicate)}).toString();}
function select(payload,value=DEFAULTS){
 if(value.invalid)return {active:false,indices:new Set(),orderedIndices:[],draws:0,note:'Invalid saved selection parameters; highlights are cleared.'};
 const s=settings(value);if(!payload||s.method==='none')return {active:false,indices:new Set(),orderedIndices:[],draws:0,note:payload?'Selection highlights are off. Cluster inspection and plot colors remain independent.':''};
 const condition=payload.conditions.find(row=>row.alpha===s.alpha&&row.tau_multiplier===s.tau_multiplier);need(condition,'The requested saved selection condition is unavailable.');
 let selected,draws,note;
 if(s.method==='panel'||s.method==='uniform'){
  selected=(s.method==='panel'?condition.panels:payload.uniform_panels)[s.replicate-1];draws=selected.length;
  note=(s.method==='panel'?'Weighted':'Uniform')+' unique panel · '+selected.length+' models · replicate '+s.replicate+'/20.';
 }else if(s.method==='disco'){
  selected=payload.disco.indices;draws=payload.disco.draws;note='Minimum-energy per-cluster control · '+selected.length+' models (one per saved structural cluster).';
 }else{
  selected=condition[s.method].indices;draws=condition[s.method].draws;
  note=(s.method==='exact'?'Exact categorical':'Metropolis–Hastings')+' · '+selected.length.toLocaleString()+' unique models visited in '+draws.toLocaleString()+' saved draws'+(s.method==='mh'?' across four retained chains':'')+'. This is not a 200-model panel.';
 }
 if(['panel','exact','mh'].includes(s.method))note+=' α='+s.alpha+' · τ/IQR='+s.tau_multiplier+'.';
 if(s.method==='mh'){note+=' Fixed-budget chains can miss clusters; compare exact categorical draws.';const d=condition.diagnostics;if(d)note+=' Cluster TV: MH '+d.mh_cluster_total_variation.toFixed(3)+' vs matched IID '+d.matched_iid_cluster_total_variation.toFixed(3)+' · '+d.unvisited_assigned_clusters+' assigned cluster'+(d.unvisited_assigned_clusters===1?'':'s')+' unvisited.';else note+=' Saved comparison diagnostics are unavailable for this older payload.';note+=' Exploratory chains; convergence is not established by these highlights.';}
 return {active:selected.length>0,method:s.method,indices:new Set(selected),orderedIndices:[...selected],draws,note,condition_id:['uniform','disco'].includes(s.method)?null:condition.id};
}
function category(scheme,i){return scheme.type==='continuous'?(Number.isFinite(scheme.values[i])?'valid':'Not calculable'):String(scheme.values[i]??'Unspecified');}
function overlayTrace(data,method,highlight,currentScheme,visible=()=>true,hidden=new Set()){
 if(!highlight?.active)return null;
 const xy=data.projections[method].xy,selected=highlight.orderedIndices.filter(i=>visible(data.clusters[i])&&!hidden.has(category(currentScheme,i))&&Number.isFinite(xy[i]?.[0])&&Number.isFinite(xy[i]?.[1]));
 return {type:'scattergl',mode:'markers',name:'Saved selection',x:selected.map(i=>xy[i][0]),y:selected.map(i=>xy[i][1]),customdata:selected,marker:{symbol:'circle-open',size:9,color:'#151515',line:{color:'#151515',width:1.8},opacity:.95},meta:{selectionHighlight:true},showlegend:false,hoverinfo:'none'};
}
const api={DEFAULTS,METHODS,createLoader,validatePayload,parseSettings,routeParams,select,overlayTrace,category};root.AISExplorerSelections=api;if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
