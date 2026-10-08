import type {Session} from './types.ts';
export type Command = 'start'|'reset'|'pause'|'resume'|'return'|'stop';
export type Notice = {kind:'accepted'|'reset'|'seed'|'network'|'response'|'api';command?:Command;code?:number;original?:string};
export function validSeed(seed:number):boolean {return Number.isInteger(seed)&&seed>=0&&seed<=2147483647}
export function commandRequest(command:Command,session:Session):{url:string;init:RequestInit} {
 const configure=command==='start'||command==='reset';
 return {url:command==='start'?'/api/missions':command==='reset'?'/api/missions/reset':'/api/command',init:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(configure?session:{command})}};
}
export async function sendCommand(command:Command,session:Session,transport:typeof fetch=fetch):Promise<Notice> {
 if((command==='start'||command==='reset')&&!validSeed(session.seed))return {kind:'seed'};
 const request=commandRequest(command,session);
 try{
  const response=await transport(request.url,request.init);
  let body:{detail?:unknown};
  const raw=await response.text();
  try{body=JSON.parse(raw)}catch{return response.ok?{kind:'response'}:{kind:'api',code:response.status,original:raw||undefined}}
  if(!response.ok)return {kind:'api',code:response.status,original:body?.detail===undefined?undefined:typeof body.detail==='string'?body.detail:JSON.stringify(body.detail)};
  return {kind:command==='reset'?'reset':'accepted',command};
 }catch{return {kind:'network'}}
}
