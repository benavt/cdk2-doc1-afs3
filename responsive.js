/* Responsive presentation of saved plot data. No scores or memberships are changed. */
(function(root){
 'use strict';
 const records=new Map(),queues=new WeakMap();let timer,working=false,again=false;
 const short=value=>String(value).replace(/^Cluster\s+/,'C');
 const tickSet=(labels,count)=>{const step=Math.max(1,Math.ceil(labels.length/count)),indices=labels.map((_,i)=>i).filter(i=>i%step===0);if(indices.at(-1)!==labels.length-1){if(indices.length>1&&labels.length-1-indices.at(-1)<step)indices.pop();indices.push(labels.length-1)}return indices.map(i=>labels[i])};
 function dimensions(node){
  const frame=node.id==='tmViolin'?node.closest?.('.plot-scroll'):null;
  const width=Math.max(1,Math.round(frame?.getBoundingClientRect().width||node.getBoundingClientRect().width||node.parentElement.getBoundingClientRect().width||root.innerWidth-32));
  return {width,small:width<600,viewport:Math.max(320,root.visualViewport?.height||root.innerHeight||800),maximized:!!node.closest('.is-maximized')};
 }
 function title(value){return typeof value==='string'?{text:value}:value||{}}
 function prepare(node,traces,layout={},config={}){
  const {width,small,viewport,maximized}=dimensions(node),matrix=traces.find(t=>t.type==='heatmap'),projection=['pca','umap','tsne'].includes(node.id),sharedLegend=node.id==='projectionLegend';
  const next={...layout,autosize:false,width,font:{...layout.font,size:small?11:12}},data=traces.map(t=>{const copy={...t};if(t.marker)copy.marker={...t.marker};else delete copy.marker;return copy});
  if(sharedLegend){
   const continuous=data.some(t=>t.marker?.showscale),legendCount=data.filter(t=>t.showlegend!==false).length;
   const entryWidth=small?.5:150,columns=small?2:Math.max(1,Math.floor((width-24)/(entryWidth+40)));
   next.height=continuous?(legendCount?112:88):Math.max(52,20+Math.ceil(legendCount/columns)*22);
   next.margin={l:8,r:8,t:8,b:8,autoexpand:false};
   next.legend={...layout.legend,orientation:'h',x:0,xanchor:'left',y:1,yanchor:'top',maxheight:1,font:{size:12},entrywidth:entryWidth,entrywidthmode:small?'fraction':'pixels'};
   for(const trace of data)if(trace.marker?.showscale)trace.marker.colorbar={...trace.marker.colorbar,orientation:'h',x:.5,xanchor:'center',y:.16,yanchor:'bottom',len:Math.min(.9,700/width),thickness:12,title:{...title(trace.marker.colorbar?.title),side:'top',font:{size:12}},tickfont:{size:11}};
  }else if(projection&&node.closest('.cluster-view')){
   const panel=node.closest('.cluster-view'),featured=panel.classList.contains('is-featured');
   next.margin=featured?{l:50,r:14,t:12,b:52}:{l:8,r:8,t:5,b:8};
   const screen=panel.closest?.('.explorer-screen'),available=screen?panel.getBoundingClientRect().height-panel.querySelector('.view-heading').getBoundingClientRect().height:null;
   next.height=available>0?Math.max(30,Math.floor(available)):featured?Math.round(Math.max(180,Math.min(width*.75+48,viewport*.65))):Math.round(Math.max(45,width*.62));
   next.showlegend=false;next.hovermode=featured?'closest':false;
   if(screen&&!featured)next.margin={l:38,r:8,t:7,b:36};
   for(const axis of ['xaxis','yaxis'])next[axis]={...layout[axis],visible:featured||!!screen,title:featured||screen?{...title(layout[axis]?.title),font:{size:11},standoff:8}:undefined,automargin:featured};
   if(!featured)for(const trace of data)if(trace.marker)trace.marker.size=2.5;
  }else if(matrix&&matrix.x?.length===matrix.y?.length){
   const labels=matrix.x,margin={l:small?52:88,r:small?14:38,t:layout.title?112:(small?82:104),b:small?72:92,autoexpand:false};
   const space=width-margin.l-margin.r,side=Math.max(100,Math.min(space,820,Math.max(160,viewport-margin.t-margin.b-(maximized?130:200))));
   const pad=Math.max(0,(space-side)/2),domain=[pad/space,1-pad/space];
   next.height=Math.round(side+margin.t+margin.b);next.margin=margin;
   const ticks=tickSet(labels,Math.max(3,Math.floor(side/(small?34:42))));
   next.xaxis={...layout.xaxis,type:'category',categoryorder:'array',categoryarray:labels,range:[-.5,labels.length-.5],autorange:false,domain,constrain:'domain',showgrid:false,zeroline:false,tickmode:'array',tickvals:ticks,ticktext:ticks.map(v=>small?short(v):String(v)),tickangle:-45,automargin:false};
   next.yaxis={...layout.yaxis,type:'category',categoryorder:'array',categoryarray:labels,range:[labels.length-.5,-.5],autorange:false,domain:[0,1],scaleanchor:'x',scaleratio:1,constrain:'domain',showgrid:false,zeroline:false,tickmode:'array',tickvals:ticks,ticktext:ticks.map(v=>small?short(v):String(v)),automargin:false};
   next.uirevision=layout.uirevision||node.id+'-'+labels.join('|');
   if(layout.title)next.title={...title(layout.title),font:{size:small?12:15},xref:'paper',x:.5,xanchor:'center',yref:'paper',y:1+(margin.t-24)/side,yanchor:'top'};
   for(const trace of data)if(trace.type==='heatmap')trace.colorbar={...trace.colorbar,orientation:'h',x:.5,xanchor:'center',y:1.025,yanchor:'bottom',len:Math.min(.88,side/space),thickness:12,outlinewidth:0,tickfont:{size:11},title:{...title(trace.colorbar?.title),side:'top',font:{size:12}}};
  }else if(node.id==='tmViolin'){
   const labels=[...new Set(data.flatMap(t=>t.x||[]))],plotWidth=Math.max(width,100+labels.length*64);
   next.width=plotWidth;next.height=540;next.showlegend=false;
   next.margin={l:72,r:24,t:28,b:125,autoexpand:false};
   next.xaxis={...layout.xaxis,type:'category',categoryorder:'array',categoryarray:labels,tickmode:'array',tickvals:labels,ticktext:labels.map(value=>String(value).replace(' · ','<br>')),tickangle:-45,automargin:false};
   next.yaxis={...layout.yaxis,title:{...title(layout.yaxis?.title),font:{size:12},standoff:12},range:[0,1],automargin:false};
   node.style.width=plotWidth+'px';
   const hint=document.getElementById('violinScrollHint');if(hint)hint.hidden=plotWidth<=width;
  }else{
   const legendCount=layout.showlegend===false?0:data.filter(t=>t.showlegend!==false&&!t.marker?.showscale).length;
   const continuous=data.some(t=>t.marker?.showscale),longLegend=small&&data.some(t=>String(t.name||'').length>18);
   if(longLegend)for(const trace of data){const words=String(trace.name||'').split(' ');let line=0;trace.name=words.map(word=>{if(line&&line+word.length>18){line=word.length;return '<br>'+word}line+=word.length+1;return word}).join(' ')}
   const columns=small?2:Math.max(1,Math.floor((width-90)/180));
   const sharedHeight=projection&&maximized?node.closest('.is-maximized').querySelector('#projectionLegend')?.getBoundingClientRect().height||0:0;
   const top=continuous?(small?112:32):legendCount?Math.max(28,Math.ceil(legendCount/columns)*(longLegend?34:22)+22):(layout.margin?.t||28);
   next.margin={...layout.margin,l:small?54:(layout.margin?.l||60),r:small?16:(layout.margin?.r||30),t:top,b:small?72:(layout.margin?.b||65)};
   next.height=projection?Math.round(Math.max(320,Math.min(maximized?viewport-180-sharedHeight:640,Math.max(250,width*.75)+top+next.margin.b))):Math.round(Math.max(340,Math.min(560,viewport-200)));
   next.xaxis={...layout.xaxis,title:{...title(layout.xaxis?.title),font:{size:small?11:13},standoff:12},automargin:true};
   next.yaxis={...layout.yaxis,title:{...title(layout.yaxis?.title),font:{size:small?11:13},standoff:8},automargin:true};
   if(node.id==='countTradeoff')next.xaxis={...next.xaxis,dtick:small?2:1,tickangle:0};
   if(small&&layout.xaxis?.type==='category'){
    const labels=[...new Set(data.flatMap(t=>t.x||[]))],ticks=tickSet(labels,Math.max(3,Math.floor((width-70)/38)));
    next.xaxis={...next.xaxis,tickmode:'array',tickvals:ticks,ticktext:ticks.map(short),tickangle:-50};
   }
   next.legend={...layout.legend,orientation:'h',x:0,xanchor:'left',y:1.02,yanchor:'bottom',font:{size:small?11:12},...(small?{entrywidth:.5,entrywidthmode:'fraction'}:{})};
   for(const trace of data)if(small&&trace.marker?.showscale)trace.marker.colorbar={...trace.marker.colorbar,orientation:'h',x:.5,xanchor:'center',y:1.13,yanchor:'bottom',len:.9,thickness:10,title:{...title(trace.marker.colorbar?.title),side:'top',font:{size:11}}};
  }
  node.style.height=next.height+'px';node.style.minWidth='0';
  return {data,layout:next,config:{...config,responsive:false,displayModeBar:projection||sharedLegend?false:!small,scrollZoom:false}};
 }
 function tools(node){
  const anchor=node.closest?.('.plot-scroll')||node;
  if(node.id==='projectionLegend'||node.closest?.('.cluster-view')||anchor.nextElementSibling?.classList.contains('plot-tools'))return;
  const bar=document.createElement('div');bar.className='plot-tools';bar.setAttribute('aria-label','Plot controls');
  for(const [text,action]of [['Reset plot',()=>reset(node)],['Save PNG',()=>root.Plotly.downloadImage(node,{format:'png',filename:node.id,width:Math.max(900,node.layout.width),height:Math.max(650,node.layout.height)})]]){
   const button=document.createElement('button');button.type='button';button.textContent=text;button.onclick=()=>Promise.resolve(action()).catch(error=>console.error(error));bar.append(button);
  }
  anchor.insertAdjacentElement('afterend',bar);
 }
 function reset(node){const saved=records.get(node);if(!saved)return;const spec=prepare(node,saved.traces,saved.layout,saved.config),update={};for(const key of ['xaxis','yaxis']){const axis=spec.layout[key]||{};if(axis.range){update[key+'.range']=[...axis.range];update[key+'.autorange']=false}else update[key+'.autorange']=axis.autorange==='reversed'?'reversed':true}return root.Plotly.relayout(node,update)}
 async function react(node,traces,layout,config){
  if(typeof node==='string')node=document.getElementById(node);
  records.set(node,{traces,layout,config});
  // Plotly mutates its render state; serialize resize and data updates per plot.
  const previous=queues.get(node)||Promise.resolve();
  const task=previous.catch(()=>{}).then(async()=>{const spec=prepare(node,traces,layout,config);const result=await root.Plotly.react(node,spec.data,spec.layout,spec.config);tools(node);if(!node.dataset.responsiveObserved){node.dataset.responsiveObserved='true';observer?.observe(node)}return result});
  queues.set(node,task);return task;
 }
 function schedule(){clearTimeout(timer);timer=setTimeout(resizeAll,150)}
 async function resizeAll(){
  if(working){again=true;return}working=true;
  try{for(const [node,spec]of records){if(!node.isConnected||!node.getBoundingClientRect().width||!node.getClientRects().length)continue;await react(node,spec.traces,spec.layout,spec.config)}}finally{working=false;if(again){again=false;schedule()}}
 }
 const widths=new WeakMap(),observer=typeof ResizeObserver==='function'?new ResizeObserver(entries=>{for(const entry of entries){const width=Math.round(entry.contentRect.width);if(width>0&&widths.get(entry.target)!==width){widths.set(entry.target,width);schedule()}}}):null;
 root.addEventListener('resize',schedule);root.visualViewport?.addEventListener('resize',schedule);
 document.addEventListener('toggle',event=>{if(event.target.open)schedule()},true);
 root.AtlasResponsive={react,resizeAll,schedule,prepare,reset};
})(window);
