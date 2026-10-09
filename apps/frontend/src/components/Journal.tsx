import {useState} from 'react';
import type {Entry} from '../types.ts';
import {useI18n} from '../i18n/index.tsx';
import {journalCategory,journalText} from '../presentation.ts';
const categories=['all','hypothesis','experiment','observation','action','model_update','replan','conclusion','safety','result'] as const;
export function Journal({entries,presentation}:{entries:Entry[];presentation:boolean}) {
 const {t,n}=useI18n();const [filter,setFilter]=useState<string>('all'),[compact,setCompact]=useState(true);
 const significant=new Set(['conclusion','model_update','replan','safety','result']);
 const visible=entries.filter(e=>presentation?significant.has(journalCategory(e)):filter==='all'||journalCategory(e)===filter).slice(presentation?-3:-150).reverse();
 return <section className={`journal ${compact?'compact':''}`}><div className="panel-head"><h2>{t(presentation?'console.significant':'journal.title')}</h2><span>{t('journal.count',{count:n(entries.length,0)})}</span></div>
 {!presentation&&<div className="journal-toolbar"><label>{t('console.journalFilter')}<select value={filter} onChange={e=>setFilter(e.target.value)}>{categories.map(k=><option key={k} value={k}>{t(`journal.${k}`)}</option>)}</select></label><label className="check"><input type="checkbox" checked={compact} onChange={e=>setCompact(e.target.checked)}/>{t('journal.compact')}</label></div>}
 <div className="journal-list">{visible.length?visible.map((e,i)=>{const body=journalText(e,t),category=journalCategory(e),known=categories.includes(category as typeof categories[number]);return <article key={`${e.sim_time}-${e.hypothesis_id}-${i}`}><time>{t('journal.time',{time:n(e.sim_time)})}</time><div className="timeline-entry"><div className="entry-meta"><span className={`stage ${category}`}>{known?t(`journal.${category}` as 'journal.action'):t('journal.observation')}</span>{e.hypothesis_id&&<code>{e.hypothesis_id}</code>}{body.original&&<small className="original-tag">{t('journal.original')}</small>}</div><details open={!compact||presentation}><summary>{body.text}</summary><div className="entry-detail"><span>{t('console.evidence')}</span><h4>{t('console.raw')}</h4><pre>{e.text}</pre></div></details></div></article>}):<div className="empty"><strong>{t('journal.empty')}</strong><small>{t('journal.emptyHint')}</small></div>}</div></section>;
}
