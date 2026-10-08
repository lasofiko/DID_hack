import test from 'node:test';
import assert from 'node:assert/strict';
import {dictionaries,number,translator,validLocale} from '../src/i18n/core.ts';
import {costAt,fitMap,gridToWorld,scaleLength,screenPath,screenToWorld,worldToScreen} from '../src/mapMath.ts';
import {decisionSource,journalCategory,journalText,reasonText,statusText} from '../src/presentation.ts';
const ru=translator('ru-RU'),tt=translator('tt-RU');
const parameters=text=>[...text.matchAll(/\{(\w+)\}/g)].map(m=>m[1]).sort();
test('RU/TT key coverage and parameter parity for every message',()=>{
 assert.deepEqual(Object.keys(dictionaries['tt-RU']).sort(),Object.keys(dictionaries['ru-RU']).sort());
 for(const [key,value] of Object.entries(dictionaries['ru-RU'])){assert.ok(dictionaries['tt-RU'][key].trim(),key);assert.deepEqual(parameters(value),parameters(dictionaries['tt-RU'][key]),key);
 for(const locale of ['ru-RU','tt-RU']){const args=Object.fromEntries(parameters(value).map(p=>[p,'123']));assert.ok(!translator(locale)(key,args).includes('{'),key)}}
});
test('invalid stored locale defaults to Russian',()=>{for(const value of [null,undefined,'en','ru','tt','garbage',{}])assert.equal(validLocale(value),'ru-RU');assert.equal(validLocale('tt-RU'),'tt-RU')});
test('locale decimal formatting preserves telemetry precision',()=>{assert.match(number('ru-RU',12.345,2),/12,35/);assert.match(number('tt-RU',12.345,2),/12[,.]35/);assert.equal(number('ru-RU',3,0),'3')});
test('Tatar alphabet occurs in dictionary and remains Unicode',()=>{const values=Object.values(dictionaries['tt-RU']).join(' ');for(const letter of 'әөүҗңһ')assert.ok(values.toLowerCase().includes(letter),letter)});
test('map coordinates round trip with screen Y inversion at multiple zooms',()=>{for(const zoom of [8,125,600]){const v={x:-2,y:.5,zoom};const p={x:2.25,y:-.75};const q=worldToScreen(p,v,800,600);assert.deepEqual(screenToWorld(q,v,800,600),p);assert.ok(worldToScreen({x:-2,y:1},v,800,600).y<300)}});
const grid={width:10,height:4,resolution:.5,origin:{x:1,y:2},origin_yaw:Math.PI/2,data:Array(40).fill(0),revision:1};
test('rotated map fit includes all corners',()=>{const v=fitMap(grid,800,600);for(const p of [{x:0,y:0},{x:5,y:0},{x:0,y:2},{x:5,y:2}]){const q=worldToScreen(gridToWorld(p,grid),v,800,600);assert.ok(q.x>=0&&q.x<=800&&q.y>=0&&q.y<=600)}});
test('energy hit test applies map yaw and 0.5 metre cell size',()=>{const cell={cell:{x:0,y:0}};assert.equal(costAt({x:.3,y:0},[cell],Math.PI/4),cell);assert.equal(costAt({x:.3,y:0},[cell],0),undefined);assert.equal(costAt({x:.6,y:.6},[cell],Math.PI/4),undefined)});
test('long trajectory keeps endpoints and visible bends',()=>{const points=Array.from({length:30000},(_,i)=>({x:i/1000,y:Math.sin(i/1000)}));const path=screenPath(points,{x:0,y:0,zoom:20},800,600);assert.ok(path.length<points.length);assert.deepEqual(path[0],{x:400,y:300});assert.deepEqual(path.at(-1),worldToScreen(points.at(-1),{x:0,y:0,zoom:20},800,600));assert.ok(path.some(p=>p.y<290))});
test('scale length remains within a readable screen range',()=>{for(const zoom of [8,30,125,600]){const length=scaleLength(zoom)*zoom;assert.ok(length>=85&&length<=170)}});
test('LLM selection does not falsify algorithmic decision source',()=>{assert.equal(decisionSource(null,ru),ru('metric.noData'));const data={session:{planner_mode:'llm'},planner_source:'Algorithmic'};assert.equal(decisionSource(data,ru),ru('planner.fallback'));data.planner_source='LLM';assert.equal(decisionSource(data,ru),'LLM');data.session.planner_mode='algorithmic';data.planner_source='Algorithmic';assert.equal(decisionSource(data,ru),ru('planner.algorithmic'))});
test('known journal messages localize; arbitrary diagnostics remain exact',()=>{assert.deepEqual(journalText({text:'LLM unavailable: using Algorithmic fallback'},tt),{text:tt('journal.fallback'),original:false});const raw="Failure: timeout on service /did/finish";assert.deepEqual(journalText({text:raw},ru),{text:raw,original:true});assert.equal(journalCategory({text:raw,stage:'observation'}),'safety');assert.equal(journalCategory({text:'Finish: {}',stage:'observation'}),'result');assert.equal(journalText({text:'Mission: failed'},ru).text,ru('state.failed'))});
test('unknown reason and status are visible without invented explanations',()=>{assert.deepEqual(reasonText('Provider diagnosis: custom',ru),{text:'Provider diagnosis: custom',original:true});assert.equal(statusText('new_state',ru),ru('state.unknown',{code:'new_state'}))});

import {commandRequest,sendCommand,validSeed} from '../src/api.ts';
const session={scenario:'medium',seed:27,mode:'adaptive',planner_mode:'llm'};
test('Start/Reset keep session contract and all commands use public API endpoints',()=>{
 for(const cmd of ['start','reset','pause','resume','return','stop']){const req=commandRequest(cmd,session);assert.equal(req.init.method,'POST');assert.deepEqual(JSON.parse(req.init.body),['start','reset'].includes(cmd)?session:{command:cmd});assert.equal(req.url,cmd==='start'?'/api/missions':cmd==='reset'?'/api/missions/reset':'/api/command')}
});
test('seed bounds reject blank/nonfinite/fractional values without blocking safety commands',async()=>{
 for(const value of [NaN,Infinity,-1,.5,2147483648])assert.equal(validSeed(value),false);
 for(const value of [0,1,2147483647])assert.equal(validSeed(value),true);
 let calls=0;const transport=async()=>{calls++;return new Response('{}',{status:200})};
 assert.equal((await sendCommand('start',{...session,seed:NaN},transport)).kind,'seed');assert.equal(calls,0);
 assert.equal((await sendCommand('stop',{...session,seed:NaN},transport)).kind,'accepted');assert.equal(calls,1);
});
test('API rejection preserves status code and exact backend diagnostic',async()=>{
 const message='ROS service /did/start is unavailable';const result=await sendCommand('start',session,async()=>new Response(JSON.stringify({detail:message}),{status:503}));assert.deepEqual(result,{kind:'api',code:503,original:message});
 assert.equal((await sendCommand('reset',session,async()=>new Response('{}'))).kind,'reset');
 assert.equal((await sendCommand('pause',session,async()=>new Response('invalid JSON'))).kind,'response');
 assert.equal((await sendCommand('pause',session,async()=>{throw Error('offline')})).kind,'network');
});
import {occupancyColor,rasterOffset} from '../src/mapMath.ts';
test('ROS bottom-first occupancy rows flip once and obstacle/free/unknown stay distinct',()=>{
 assert.equal(rasterOffset(0,2,3),16);assert.equal(rasterOffset(1,2,3),20);assert.equal(rasterOffset(4,2,3),0);assert.equal(rasterOffset(5,2,3),4);
 assert.notDeepEqual(occupancyColor(-1),occupancyColor(0));assert.notDeepEqual(occupancyColor(0),occupancyColor(100));assert.deepEqual(occupancyColor(50),occupancyColor(100));
});
