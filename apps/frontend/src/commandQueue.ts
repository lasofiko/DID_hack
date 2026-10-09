import {sendCommand,type Command,type Notice} from './api.ts';
import type {Session} from './types.ts';
export type QueueState={pending:Command|null;stopQueued:boolean};
// Single client dispatch. Stop can occupy the next slot, never duplicate/overlap it.
// Abort/timeout only ends client waiting; backend operation_lock remains authoritative.
export class CommandQueue {
 private current:Command|null=null;
 private nextStop:Session|null=null;
 private change:(state:QueueState)=>void;
 private result:(command:Command,notice:Notice)=>void;
 private send:typeof sendCommand;
 constructor(change:(state:QueueState)=>void,result:(command:Command,notice:Notice)=>void,send=sendCommand){this.change=change;this.result=result;this.send=send}
 request(command:Command,session:Session):boolean {
  if(this.current){if(command==='stop'&&this.current!=='stop'&&!this.nextStop){this.nextStop={...session};this.emit();return true}return false}
  this.current=command;this.emit();void this.run(command,{...session});return true;
 }
 private emit(){this.change({pending:this.current,stopQueued:!!this.nextStop})}
 private async run(command:Command,session:Session){
  try{this.result(command,await this.send(command,session))}catch{this.result(command,{kind:'network',command})}
  finally{const next=this.nextStop;this.nextStop=null;this.current=next?'stop':null;this.emit();if(next)void this.run('stop',next)}
 }
}
