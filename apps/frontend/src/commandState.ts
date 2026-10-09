import type {Command,Notice} from './api.ts';
import type {Session,Telemetry} from './types.ts';
export const expectedStatus:Partial<Record<Command,string>>={start:'running',pause:'paused',resume:'running',return:'returning',stop:'stopped',reset:'idle'};
export function reconcileCommand(command:Command,previousStatus:string,session:Session,data:Telemetry,notice:Notice|null,fresh:boolean):'confirmed'|'terminal'|'waiting' {
 if(!fresh)return 'waiting';
 const status=data.state.status;
 // Idle + same config cannot prove a new generation. Reset needs HTTP completion too.
 if(command==='reset')return notice?.kind==='reset'&&status==='idle'&&JSON.stringify(data.session)===JSON.stringify(session)?'confirmed':'waiting';
 const accepted=notice?.kind==='accepted'&&notice.command===command;
 if(status===expectedStatus[command]&&(status!==previousStatus||accepted))return 'confirmed';
 if(['finished','failed','stopped'].includes(status)&&(status!==previousStatus||accepted))return 'terminal';
 return 'waiting';
}
