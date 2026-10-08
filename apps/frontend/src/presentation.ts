import type {Key,Translator} from './i18n/core.ts';
import type {Entry,Telemetry} from './types.ts';
const statuses:Record<string,Key>={idle:'state.idle',running:'state.running',paused:'state.paused',returning:'state.returning',finished:'state.finished',failed:'state.failed',stopped:'state.stopped'};
const actions:Record<string,Key>={explore:'action.explore',go_to:'action.go_to',collect:'action.collect',return_to_base:'action.return_to_base'};
const reasons:Record<string,Key>={'Signal-guided coverage':'reason.signal','Confirmed median signal':'reason.confirmed','Coverage exhausted':'reason.coverage','Return priority':'reason.return'};
// Exact backend-authored messages only. Arbitrary prose and Python diagnostic payloads stay verbatim.
const messages:Record<string,Key>={
 'LLM unavailable: using Algorithmic fallback':'journal.fallback',
 'Maria EnergyModel updated; adaptive route costs enabled':'journal.updateAdaptive',
 'Maria EnergyModel updated; baseline planning priors unchanged':'journal.updateBaseline',
 'Measured cost update: recompute A* route to current target':'journal.replanCurrent',
 'Measured cost update: recompute A* route':'journal.replanRoute',
 'Energy reserve: return':'journal.reserve',
 'Return path recomputed after measured cost update':'journal.replanReturn',
 'EnergyModel rejected interval; retaining conservative route costs':'journal.reject',
 'Measured cost disagrees with previous prediction; hypothesis: estimate may be stale':'journal.staleEstimate',
 'Hypothesis: isolated move interval can measure local energy cost':'journal.moveHypothesis',
 'Hypothesis: isolated turn interval can measure local energy cost':'journal.turnHypothesis',
 'Passive bounded experiment during ordinary safe move; reject transitions and cell crossings':'journal.moveExperiment',
 'Passive bounded experiment during ordinary safe turn; reject transitions and cell crossings':'journal.turnExperiment',
 'Single-cell movement estimate from actual battery/path/yaw; sample spread retained':'journal.moveConclusion',
 'Single-cell turn estimate from actual battery/path/yaw; sample spread retained':'journal.turnConclusion',
};
export function statusText(code:string,t:Translator):string {return statuses[code]?t(statuses[code] as 'state.idle'):t('state.unknown',{code})}
export function actionText(code:string|undefined,t:Translator):string {return !code?t('agent.wait'):actions[code]?t(actions[code] as 'action.explore'):code}
export function reasonText(reason:string|undefined,t:Translator):{text:string;original:boolean} {return {text:reason?(reasons[reason]?t(reasons[reason] as 'reason.signal'):reason):t('agent.noReason'),original:!!reason&&!reasons[reason]}}
export function decisionSource(data:Telemetry|null,t:Translator):string {
 if(!data)return t('metric.noData');
 if(data.planner_source==='LLM')return 'LLM';
 if(data.planner_source==='Algorithmic')return t(data.session.planner_mode==='llm'?'planner.fallback':'planner.algorithmic');
 return data.planner_source||t('metric.noData');
}
export function journalCategory(e:Entry):string {
 if(e.text.startsWith('Failure:'))return 'safety';
 if(e.text.startsWith('Finish:')||e.text.startsWith('Mission:'))return 'result';
 if(e.text.startsWith('Command:')||e.text.startsWith('Decision:')||e.text.startsWith('Navigation:')||e.text.startsWith('Collect:'))return 'action';
 return e.stage;
}
export function journalText(e:Entry,t:Translator):{text:string;original:boolean} {
 const key=messages[e.text];if(key)return {text:t(key as 'journal.fallback'),original:false};
 const command=/^Command: (pause|resume|return|stop)$/.exec(e.text);
 if(command)return {text:t('mission.accepted',{command:t(`mission.${command[1]}` as 'mission.pause')}),original:false};
 const status=/^Mission: (idle|running|paused|returning|finished|failed|stopped)$/.exec(e.text);
 if(status)return {text:statusText(status[1],t),original:false};
 return {text:e.text,original:true};
}
