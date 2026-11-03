/* Versioned reference context and project write-up placeholders, independent of plot data. */
(() => {
 'use strict';
 const content=document.getElementById('targetContextContent');
 let currentTarget=null;
 const source=new URL('target-context.json',document.currentScript.src);
 const records=fetch(source).then(response=>{if(!response.ok)throw Error('Target context unavailable');return response.json()}).catch(()=>null);
 function element(tag,text,className){const node=document.createElement(tag);if(text)node.textContent=text;if(className)node.className=className;return node}
 function reference(record){
  const link=element('a',record.label),url=new URL(record.url);if(url.protocol!=='https:')throw Error('Reference links must use HTTPS');
  link.href=url.href;link.target='_blank';link.rel='noopener noreferrer';return link;
 }
 function render(target,entry,verifiedOn){
  content.replaceChildren(element('h3',entry.title));
  if(entry.organism)content.append(element('p',entry.organism,'context-organism'));
  content.append(element('p',entry.record_summary,'context-summary'));
  const project=entry.project_writeup;
  content.append(element('h4','Project notes'));
  if(project.biological_relevance)content.append(element('p',project.biological_relevance));
  if(project.ensemble_interpretation)content.append(element('p',project.ensemble_interpretation));
  if(!project.biological_relevance&&!project.ensemble_interpretation)content.append(element('p','Pending.','writeup-placeholder'));
  content.append(element('h4','References'));
  const links=element('ul');links.className='context-references';
  for(const record of [...entry.references,...project.project_citations]){const item=element('li');item.append(reference(record));links.append(item)}
  if(project.project_record_url){const item=element('li');item.append(reference({label:'Project record',url:project.project_record_url}));links.append(item)}
  content.append(links);
  for(const review of entry.review_notes||[]){const details=element('details');details.className='reference-review';details.append(element('summary','Annotation under review'),element('p',review.note));content.append(details)}
  const provenance=element('details');provenance.className='context-provenance';provenance.append(element('summary','Record details'),element('p','References checked '+verifiedOn+' · '+project.status));content.append(provenance);
  document.getElementById('targetContext').dataset.target=target;
 }
 window.addEventListener('atlas:cohort',async event=>{
  const current=event.detail.current,target=current.target;currentTarget=target;const sequence=current.provenance?.sequence_sha256||current.provenance?.original_parent_provenance?.sequence_sha256;
  content.replaceChildren(element('h3',target.split('_')[0]),element('p','Loading…'));
  try{const metadata=await records;if(currentTarget!==target)return;const entry=metadata.targets[target];if(!entry)throw Error('Target context unavailable');const recorded=entry.provenance?.analysis_sequence_sha256;if(!sequence||!recorded||sequence!==recorded)throw Error('Target sequence does not match the context record');render(target,entry,metadata.verified_on)}
  catch(error){if(currentTarget===target)content.replaceChildren(element('h3',target.split('_')[0]+' · Target context'),element('p','No reference records available.'))}
 });
})();
