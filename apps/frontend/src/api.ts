import type {Session} from './types.ts';
export type Command = 'start'|'reset'|'pause'|'resume'|'return'|'stop';
export type Notice = {kind:'accepted'|'reset'|'seed'|'network'|'response'|'api'|'timeout';command?:Command;code?:number;original?:string};
export function validSeed(seed:number):boolean {return Number.isInteger(seed)&&seed>=0&&seed<=2147483647}
export function commandRequest(command:Command,session:Session):{url:string;init:RequestInit} {
 const configure=command==='start'||command==='reset';
 return {url:command==='start'?'/api/missions':command==='reset'?'/api/missions/reset':'/api/command',init:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(configure?session:{command})}};
}
export async function sendCommand(command:Command,session:Session,transport:typeof fetch=fetch,timeoutMs=command==='start'||command==='reset'?90000:12000):Promise<Notice> {
 if((command==='start'||command==='reset')&&!validSeed(session.seed))return {kind:'seed'};
 const request=commandRequest(command,session);
 const controller=new AbortController();let expired=false;
 let timer:ReturnType<typeof setTimeout>;
 const deadline=new Promise<never>((_,reject)=>{timer=setTimeout(()=>{expired=true;controller.abort();reject(new Error('deadline'))},timeoutMs)});
 try{
  const response=await Promise.race([transport(request.url,{...request.init,signal:controller.signal}),deadline]);
  let body:{detail?:unknown};
  const raw=await Promise.race([response.text(),deadline]);
  try{body=JSON.parse(raw)}catch{return response.ok?{kind:'response'}:{kind:'api',code:response.status,original:raw||undefined}}
  if(!response.ok)return {kind:'api',code:response.status,original:body?.detail===undefined?undefined:typeof body.detail==='string'?body.detail:JSON.stringify(body.detail)};
  return {kind:command==='reset'?'reset':'accepted',command};
 }catch{return {kind:expired?'timeout':'network',command}}finally{clearTimeout(timer!)}
}
