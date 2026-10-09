import React,{useEffect,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {I18nProvider,useI18n} from './i18n/index.tsx';
import {WorldMap} from './components/WorldMap.tsx';
import {EnergyPanel} from './components/EnergyPanel.tsx';
import {Journal} from './components/Journal.tsx';
import {Icon} from './components/Icon.tsx';
import {actionText,decisionSource,reasonText,statusText} from './presentation.ts';
import {reconcileCommand,expectedStatus} from './commandState.ts';
import {CommandQueue,type QueueState} from './commandQueue.ts';
import type {Cost,Grid,Session,Telemetry} from './types.ts';
import type {Key} from './i18n/core.ts';
import type {Command,Notice} from './api.ts';
import './style.css';
const INITIAL:Session={scenario:'easy',seed:1,mode:'baseline',planner_mode:'algorithmic'};
const commandKeys:Record<Command,Key>={start:'mission.start',pause:'mission.pause',resume:'mission.resume',return:'mission.return',stop:'mission.stop',reset:'mission.reset'};
const terminal=(status:string)=>['finished','failed','stopped'].includes(status);
function App(){
 const {t,n,locale,setLocale}=useI18n();
 const [data,setData]=useState<Telemetry|null>(null),[grid,setGrid]=useState<Grid|null>(null),[session,setSession]=useState(INITIAL);
 const [mapAttempt,setMapAttempt]=useState(0),[socket,setSocket]=useState('connecting'),[mapError,setMapError]=useState(false);
 const [notice,setNotice]=useState<Notice|null>(null),[queueState,setQueueState]=useState<QueueState>({pending:null,stopQueued:false});
 const [presentation,setPresentation]=useState(false),[cost,setCost]=useState<Cost|null>(null),[relative,setRelative]=useState(false);
 const [uncertain,setUncertain]=useState(false),[awaiting,setAwaiting]=useState<Command|null>(null),[stopRequested,setStopRequested]=useState(false);
 const [resetPending,setResetPending]=useState(false);
 const received=useRef(0),stopAt=useRef(0),requestStatus=useRef('idle'),requestSession=useRef(INITIAL),requestAt=useRef(0),resetDialog=useRef<HTMLDialogElement>(null);
 const queue=useRef<CommandQueue|null>(null);
 if(!queue.current)queue.current=new CommandQueue(setQueueState,(cmd,result)=>{
  setNotice(result);
  if(['network','timeout','response'].includes(result.kind)||result.kind==='api'&&(result.code??0)>=500)setUncertain(true);
  if(result.kind==='seed'||result.kind==='api'&&(result.code??0)<500){setAwaiting(null);if(cmd==='stop')setStopRequested(false)}
  if(result.kind==='reset'){setGrid(null);setCost(null);setMapAttempt(v=>v+1)}
 });
 useEffect(()=>{if(resetPending)resetDialog.current?.showModal();else resetDialog.current?.close()},[resetPending]);
 useEffect(()=>{let ws:WebSocket,timer:ReturnType<typeof setTimeout>,alive=true;
  function connect(){if(!alive)return;setSocket('connecting');ws=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/api/telemetry`);
   ws.onmessage=e=>{if(!alive)return;try{const value=JSON.parse(e.data) as Telemetry;if(!value.state||!value.session||!Array.isArray(value.journal)||!Array.isArray(value.knowledge))throw Error('Invalid telemetry');received.current=Date.now();setData(value);setSocket('online')}catch{setSocket('error')}};
   ws.onerror=()=>{if(alive)setSocket('error')};ws.onclose=()=>{if(alive){setSocket('offline');timer=setTimeout(connect,2000)}}}
  connect();const stale=setInterval(()=>{if(received.current&&Date.now()-received.current>2000)setSocket('offline')},500);
  return()=>{alive=false;clearTimeout(timer);clearInterval(stale);ws?.close()};
 },[]);
 useEffect(()=>{const controller=new AbortController();setGrid(null);setMapError(false);if(!data?.map_revision)return;
  fetch('/api/map',{signal:controller.signal}).then(r=>{if(!r.ok)throw Error('Map unavailable');return r.json()}).then((value:Grid)=>{if(!value.width||!value.height||!value.resolution||!Array.isArray(value.data)||value.data.length!==value.width*value.height)throw Error('Invalid map');setGrid(value)}).catch(()=>{if(!controller.signal.aborted)setMapError(true)});return()=>controller.abort();
 },[data?.map_revision,data?.session.seed,data?.session.scenario,mapAttempt]);
 useEffect(()=>{if(!presentation)return;const handler=(event:KeyboardEvent)=>{if(event.key==='Escape')setPresentation(false)};window.addEventListener('keydown',handler);return()=>window.removeEventListener('keydown',handler)},[presentation]);
 const connection=socket==='online'?(data?.connection||'connecting'):socket,online=connection==='online';
 const status=data?.state.status||'idle',active=['running','paused','returning'].includes(status),obs=data?.state.observation;
 const busy=!!queueState.pending,finished=terminal(status);
 const expected=expectedStatus;
 const confirmed=online&&stopRequested&&received.current>stopAt.current&&status==='stopped';
 useEffect(()=>{
  if(!online||queueState.pending||!awaiting||!data)return;
  const resolution=reconcileCommand(awaiting,requestStatus.current,requestSession.current,data,notice,received.current>requestAt.current);
  if(resolution!=='waiting'){setAwaiting(null);setUncertain(false);if(resolution==='terminal'||notice?.kind!=='accepted')setNotice(null)}
 },[data,online,queueState.pending,awaiting,notice]);
 useEffect(()=>{
  if(queueState.pending||!awaiting)return;
  const timer=setTimeout(()=>{setUncertain(true);if(awaiting!=='reset')setAwaiting(null)},15000);
  return()=>clearTimeout(timer);
 },[queueState.pending,awaiting]);
 const total=({easy:3,medium:5,hard:7} as Record<string,number>)[data?.session.scenario||session.scenario]??0;
 function action(cmd:Command,confirmedReset=false){
  if(cmd==='reset'&&!confirmedReset){setResetPending(true);return}
  if(cmd==='stop'){if(queueState.pending==='stop'||queueState.stopQueued||confirmed)return;stopAt.current=Date.now();setStopRequested(true)}
  if(queue.current!.request(cmd,session)){
   requestStatus.current=status;requestSession.current={...session};requestAt.current=Date.now();setNotice(null);setAwaiting(cmd);
   if(cmd==='start'||cmd==='reset'){setStopRequested(false);setCost(null)}
  }
 }
 const source=decisionSource(data,t),reason=reasonText(data?.state.goal?.reason,t);
 const objective=active?actionText(data?.state.goal?.action,t):status==='idle'?t('agent.wait'):statusText(status,t);
 const commandName=(cmd:Command)=>t(commandKeys[cmd] as 'mission.start');
 const unknown=uncertain||notice&&['network','timeout','response'].includes(notice.kind);
 const noticeText=queueState.stopQueued?t('console.stopQueued'):confirmed?t('console.stopConfirmed'):queueState.pending==='stop'?t('console.stopSent'):busy?t('console.wait',{command:commandName(queueState.pending!)}):notice?.kind==='accepted'?(online&&!awaiting&&status===expected[notice.command||'start']?t('console.commandConfirmed',{command:commandName(notice.command||'start')}):t('console.apiAccepted',{command:commandName(notice.command||'start')})):notice?.kind==='reset'?t('mission.resetDone'):notice?.kind==='seed'?t('mission.seedError'):notice?.kind==='timeout'?t('console.timeout'):notice?.kind==='network'?t('console.network'):notice?.kind==='response'?t('mission.responseError'):notice?.kind==='api'?t('mission.requestError',{code:n(notice.code||0,0)}):t('console.ready');
 const lastEvent=data?.events?.at(-1),eventKeys:Record<string,Key>={sample_collected:'event.sample_collected',false_collect:'event.false_collect',hazard_hit:'event.hazard_hit',collision:'event.collision'};
 const failure=data?.error||[...(data?.journal||[])].reverse().find(e=>e.text.startsWith('Failure:'))?.text;
 const result=data&&finished?(status==='finished'?t('agent.complete',{delivered:n(data.state.delivered,0),total:n(total,0)}):statusText(status,t)):lastEvent?(eventKeys[lastEvent.type]?t(eventKeys[lastEvent.type] as 'event.collision'):lastEvent.type):t('console.resultWait');
 const lock=busy||uncertain||!!awaiting;
 const stopAvailable=(active||queueState.pending==='start'||queueState.pending==='resume'||(awaiting&&awaiting!=='reset'))&&!confirmed&&queueState.pending!=='stop'&&!queueState.stopQueued;
 const sessionLabel=(value:Session)=>t('app.session',{scenario:t(`scenario.${value.scenario}` as 'scenario.easy'),seed:Number.isFinite(value.seed)?n(value.seed,0):'—'});
 return <main className={presentation?'presentation':''}>
  <div className="operator-chrome"><header>
   <a className="brand" href="#mission-map"><svg className="brandmark" viewBox="0 0 36 36" fill="none" aria-hidden="true"><path d="M7 7h10a11 11 0 0 1 0 22H7V7Z" stroke="currentColor" strokeWidth="3"/><path d="M16 13v10m7-10v10" stroke="currentColor" strokeWidth="2"/></svg><strong>DID LAB</strong><span>TurtleBot3</span></a>
   <div className="header-state"><div className={`connection ${connection}`} role="status"><i/>{t(`connection.${['online','offline','error'].includes(connection)?connection:'connecting'}` as 'connection.online')}</div><span className={`status ${status}`}>{statusText(status,t)}</span><div className={`energy-readout ${(obs?.battery??60)<8?'low':''}`}><span>{t('metric.energy')}</span><strong>{obs?n(obs.battery):'—'}<small> / 60</small></strong><div className="battery"><i style={{width:`${Math.max(0,Math.min(100,(obs?.battery??0)/60*100))}%`}}/></div></div></div>
   <div className="header-actions"><div className="language-switch" role="group" aria-label={t('app.language')}><button lang="ru" aria-pressed={locale==='ru-RU'} onClick={()=>setLocale('ru-RU')}>RU</button><button lang="tt" aria-pressed={locale==='tt-RU'} onClick={()=>setLocale('tt-RU')}>TT</button></div><button className="presentation-toggle" aria-label={t(presentation?'app.exit':'app.presentation')} aria-pressed={presentation} onClick={()=>{setPresentation(v=>!v);window.scrollTo({top:0,behavior:'instant'})}}><Icon name={presentation?'close':'expand'}/><span>{t(presentation?'app.exit':'app.presentation')}</span></button></div>
  </header>
  <section className="command-strip" aria-label={t('mission.title')}>
   <div className="mission-identity"><strong>{t(finished?'console.last':'console.current')}</strong><span>{data?sessionLabel(data.session):t('console.noTelemetry')}</span></div>
   <div className="command-buttons">
    {!active&&<button className="primary" disabled={!online||lock} onClick={()=>action('start')}><Icon name="play"/>{t('mission.start')}</button>}
    {status==='paused'?<button disabled={!online||lock} onClick={()=>action('resume')}><Icon name="play"/>{t('mission.resume')}</button>:<button disabled={!online||lock||!['running','returning'].includes(status)} onClick={()=>action('pause')}><Icon name="pause"/>{t('mission.pause')}</button>}
    <button disabled={!online||lock||!active||status==='returning'} onClick={()=>action('return')}><Icon name="home"/><span>{t('mission.return')}</span></button>
    <button className="danger stop" disabled={!stopAvailable} onClick={()=>action('stop')}><Icon name="stop"/>{t('console.stopLabel')}</button>
   </div>
  </section></div>
  <div className={`command-feedback ${unknown?'warning':''} ${confirmed?'confirmed':''}`} role={unknown||notice?.kind==='api'?'alert':'status'}><span>{noticeText}</span>{(!online&&data)&&<span>{t('console.stale')}</span>}{unknown&&<span>{t('console.unknown')}</span>}</div>
  <div className="workspace">
   <section className="map-panel" id="mission-map"><div className="panel-head"><h1>{t('map.title')}</h1><span>{t(finished?'console.planHistory':'map.frame')}</span></div><WorldMap data={data} grid={grid} online={online} presentation={presentation} onInspect={setCost} relative={relative}/>{mapError&&<div className="map-error" role="alert">{t('map.unavailable')} <button disabled={!online} onClick={()=>setMapAttempt(v=>v+1)}>{t('map.retry')}</button></div>}
    <div className="map-summary"><span>{t(grid?'console.mapReady':'console.mapMissing')}</span><span>{data?.robot_pose?t('console.pose',{x:n(data.robot_pose.x,2),y:n(data.robot_pose.y,2),yaw:n(data.robot_yaw*180/Math.PI,0)}):t('metric.noData')}</span><span>{t('console.routeSummary',{count:n(data?.planned_path?.length||0,0),visited:n(data?.trajectory?.length||0,0)})}</span></div>
   </section>
   <aside className="decision"><div className="panel-head"><h2>{t(active?'agent.title':finished?'console.history':'console.heading')}</h2><span className="source-chip">{source}</span></div>
    <div className="decision-body"><h3>{objective}</h3>{active&&data?.state.goal?.target&&<p className="target-position">{t('map.position',{x:n(data.state.goal.target.x,2),y:n(data.state.goal.target.y,2)})}</p>}
     <div className="explanation"><h4>{t(active?'console.reason':finished?'console.history':'console.next')}</h4><p>{status==='idle'?t('console.idle'):reason.text}</p>{reason.original&&status!=='idle'&&<small className="original-tag">{t('journal.original')}</small>}</div>
     <div className="progress-summary" aria-label={t('console.progress')}><div><span>{t('metric.collected')}</span><strong>{data?n(data.state.collected,0):'—'}<small> / {n(total,0)}</small></strong></div><div><span>{t('console.delivered')}</span><strong>{data?n(data.state.delivered,0):'—'}<small> / {n(total,0)}</small></strong></div></div>
     <div className="result-summary"><h4>{t(online?'console.result':'console.lastEvent')}</h4><p>{result}</p>{lastEvent&&<time>{t('journal.time',{time:n(lastEvent.sim_time)})}</time>}</div>
     <dl><div><dt>{t('mission.strategy')}</dt><dd>{data?t(data.session.mode==='adaptive'?'mode.adaptive':'mode.baseline'):'—'}</dd></div><div><dt>{t(online?'console.signal':'console.lastSignal')}</dt><dd>{obs?n(obs.signal,3):'—'}</dd></div><div><dt>{t('mission.time',{time:obs?n(obs.sim_time):'—'})}</dt><dd>ROS</dd></div></dl>
     {!online&&<p className="stale-note">{t('console.stale')}</p>}{failure&&<div className="safety" role="alert"><strong>{t('console.failed')}</strong><p>{failure}</p><small>{t('journal.original')}</small><p>{t('console.recovery')}</p></div>}
    </div>
   </aside>
  </div>
  {presentation&&<section className="presentation-cycle" aria-label={t('console.heading')}>
   <div><h2>{t('console.observation')}</h2><p>{obs?`${t('console.signal')}: ${n(obs.signal,3)}`:t('metric.noData')}</p><small>{t('console.signalHint')}</small></div>
   <div><h2>{t('console.decision')}</h2><p>{status==='idle'?t('agent.noReason'):reason.text}</p><small>{source}{!active?` · ${t('console.history')}`:''}</small></div>
   <div><h2>{t('console.action')}</h2><p>{objective}</p><small>{online?t('mission.state'):t('console.stale')}</small></div>
   <div><h2>{t('console.result')}</h2><p>{result}</p><small>{lastEvent?t('journal.time',{time:n(lastEvent.sim_time)}):t('metric.confirmed')}</small></div>
  </section>}
  <div className="research-row"><EnergyPanel data={data} selected={cost} onSelect={setCost} relative={relative} onRelative={setRelative}/><Journal entries={data?.journal||[]} presentation={presentation}/></div>
  <div className="secondary-row"><section className="configuration"><div className="panel-head"><h2>{t('console.next')}</h2><span>{sessionLabel(session)}</span></div><p className="section-note">{t('console.nextHint')}</p><div className="settings">
   <fieldset disabled={active||busy||uncertain||!!awaiting}><legend>{t('mission.scenario')}</legend><div className="scenario-buttons">{['easy','medium','hard'].map(s=><button key={s} className={session.scenario===s?'selected':''} aria-pressed={session.scenario===s} onClick={()=>setSession(v=>({...v,scenario:s}))}>{t(`scenario.${s}` as 'scenario.easy')}</button>)}</div><p className="hint">{t(`scenario.${session.scenario}Hint` as 'scenario.easyHint')}</p><div className="setting-grid"><label>{t('mission.seed')}<input type="number" min="0" max="2147483647" step="1" value={Number.isNaN(session.seed)?'':session.seed} onChange={e=>setSession(v=>({...v,seed:e.target.value===''?NaN:Number(e.target.value)}))}/></label><label>{t('mission.strategy')}<select value={session.mode} onChange={e=>setSession(v=>({...v,mode:e.target.value}))}><option value="baseline">{t('mode.baseline')}</option><option value="adaptive">{t('mode.adaptive')}</option></select></label><label>{t('mission.planner')}<select value={session.planner_mode} onChange={e=>setSession(v=>({...v,planner_mode:e.target.value}))}><option value="algorithmic">{t('planner.algorithmic')}</option><option value="llm">{t('planner.llm')}</option></select></label></div><p className="hint">{t('planner.hint')}</p></fieldset>
   <button className="reset" disabled={busy||!!awaiting} onClick={()=>action('reset')}><Icon name="reset"/>{t('mission.reset')}</button><span className="hint">{t('console.resetHint')}</span>
  </div></section>
  <details className="diagnostic-panel"><summary>{t('console.diagnostics')}</summary><div><p>{noticeText}</p>{unknown&&<p>{t('console.unknown')}</p>}<p>{t('console.recovery')}</p>{notice?.original&&<><h4>{t('journal.original')}</h4><pre>{notice.original}</pre></>}{failure&&<pre>{failure}</pre>}<p>{t('console.signalHint')}</p></div></details></div>
  <footer><span>DID LAB / DID HACK 2026</span><span>{t('app.public')}</span></footer>
  <dialog ref={resetDialog} className="reset-dialog" aria-labelledby="reset-title" aria-describedby="reset-description" onCancel={()=>setResetPending(false)}><h2 id="reset-title">{t('mission.confirmTitle')}</h2><p id="reset-description">{t('mission.confirmReset')}</p><div className="button-row"><button autoFocus onClick={()=>setResetPending(false)}>{t('mission.cancel')}</button><button className="danger" onClick={()=>{setResetPending(false);action('reset',true)}}>{t('mission.reset')}</button></div></dialog>
 </main>;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><I18nProvider><App/></I18nProvider></React.StrictMode>);
