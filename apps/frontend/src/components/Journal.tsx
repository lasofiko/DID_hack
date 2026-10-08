import {useState} from 'react';
import type {Entry} from '../types.ts';
import {useI18n} from '../i18n/index.tsx';
import {journalCategory,journalText} from '../presentation.ts';
const categories=['all','hypothesis','experiment','observation','action','model_update','replan','conclusion','safety','result'] as const;
export function Journal({entries,presentation}:{entries:Entry[];presentation:boolean}) {
 const {t,n}=useI18n();const [filter,setFilter]=useState<string>('all'),[compact,setCompact]=useState(true);
 const visible=entries.filter(e=>presentation||filter==='all'||journalCategory(e)===filter).slice(presentation?-5:-150).reverse();
 return <section className={`panel journal ${compact?'compact':''}`}><div className="panel-head"><h2>{t('journal.title')}</h2><span>{t('journal.count',{count:n(entries.length,0)})}</span></div>
 {!presentation&&<div className="journal-toolbar"><div className="tabs" role="group" aria-label={t('journal.title')}>{categories.map(k=><button key={k} aria-pressed={filter===k} className={filter===k?'selected':''} onClick={()=>setFilter(k)}>{t(`journal.${k}`)}</button>)}</div><label><input type="checkbox" checked={compact} onChange={e=>setCompact(e.target.checked)}/>{t('journal.compact')}</label></div>}
 <div className="journal-list">{visible.length?visible.map((e,i)=>{const body=journalText(e,t),category=journalCategory(e),known=categories.includes(category as typeof categories[number]);return <article key={`${e.sim_time}-${e.hypothesis_id}-${i}`}><time>{t('journal.time',{time:n(e.sim_time)})}</time><div><span className={`stage ${category}`}>{known?t(`journal.${category}` as 'journal.action'):t('journal.observation')}</span>{body.original&&<small className="original-tag">{t('journal.original')}</small>}</div><details open={!compact||presentation}><summary>{body.text}</summary><div className="entry-detail"><span>{t('journal.evidence')}</span>{e.hypothesis_id&&<code>{e.hypothesis_id}</code>}<p>{body.original?e.text:t('journal.details')}</p></div></details></article>}):<div className="empty">◎<strong>{t('journal.empty')}</strong><small>{t('journal.emptyHint')}</small></div>}</div></section>;
}
