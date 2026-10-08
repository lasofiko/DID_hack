// Test-only public API fixture. Never imported into the application or production bundle.
// All values below are synthetic test inputs, not a robot run or judge evidence.
import {createServer} from 'node:http';
import {createHash} from 'node:crypto';
const peers=new Set(),requests=[];
const grid={width:120,height:100,resolution:.05,origin:{x:-3,y:-2.5},origin_yaw:0,revision:1,data:Array.from({length:12000},(_,i)=>{const x=i%120,y=Math.floor(i/120);return x<2||x>117||y<2||y>97||(x>50&&x<55&&y>20&&y<65)?100:0})};
let data={connection:'online',session:{scenario:'easy',seed:1,mode:'baseline',planner_mode:'algorithmic'},state:{status:'idle',collected:1,delivered:0,goal:{action:'explore',target:{x:1.4,y:1.2},reason:'Signal-guided coverage'},observation:{battery:43.2,signal:.375,sim_time:42.5}},robot_pose:{x:-.7,y:.6},robot_yaw:Math.PI/4,trajectory:[{x:-2,y:-.5},{x:-1.8,y:-.3},{x:-1.4,y:-.3},{x:-1.4,y:.2},{x:-.7,y:.6}],planned_path:[{x:-.7,y:.6},{x:-.6,y:1.2},{x:1.4,y:1.2}],knowledge:[{cell:{x:-1.75,y:-.25},energy_per_m:3.1,uncertainty:.12,energy_per_rad:null,turn_uncertainty:null,move_samples:4,turn_samples:0},{cell:{x:-1.25,y:-.25},energy_per_m:8.2,uncertainty:.7,energy_per_rad:.9,turn_uncertainty:.1,move_samples:6,turn_samples:3},{cell:{x:-1.25,y:.25},energy_per_m:5.4,uncertainty:null,energy_per_rad:null,turn_uncertainty:null,move_samples:3,turn_samples:0},{cell:{x:-.75,y:.75},energy_per_m:3,uncertainty:null,energy_per_rad:1,turn_uncertainty:.2,move_samples:0,turn_samples:2}],energy_diagnostics:{accepted:18,rejected:{sensor_skew:2},model:'Maria EnergyModel',adaptive:false},journal:[{sim_time:5,stage:'hypothesis',text:'Hypothesis: isolated move interval can measure local energy cost',hypothesis_id:'energy-1'},{sim_time:12,stage:'observation',text:"Measured movement: {'energy_used': 0.8}; battery receipt-clock skew bounded, odom approximation",hypothesis_id:'energy-1'},{sim_time:13,stage:'model_update',text:'Maria EnergyModel updated; baseline planning priors unchanged',hypothesis_id:'energy-1'},{sim_time:30,stage:'replan',text:'Measured cost update: recompute A* route to current target',hypothesis_id:''}],planner_source:'Algorithmic',collected_positions:[{x:-1.4,y:-.3}],events:[{type:'sample_collected',sim_time:25}],map_revision:1,error:null};
function frame(value){const bytes=Buffer.from(JSON.stringify(value));const head=bytes.length<126?Buffer.from([0x81,bytes.length]):Buffer.from([0x81,126,bytes.length>>8,bytes.length&255]);return Buffer.concat([head,bytes])}
const server=createServer((req,res)=>{
 res.setHeader('Content-Type','application/json');let body='';req.on('data',b=>body+=b);req.on('end',()=>{
 if(req.url==='/api/map'){res.end(JSON.stringify(grid));return}
 if(req.url==='/__test/requests'){res.end(JSON.stringify(requests));return}
 if(req.url==='/__test/state'&&req.method==='POST'){data={...data,...JSON.parse(body)};res.end('{}');return}
 if(req.method==='POST'){
 const payload=JSON.parse(body);requests.push({path:req.url,body:payload});
 if(req.url==='/api/missions'||req.url==='/api/missions/reset'){data.session=payload;data.state.status=req.url.endsWith('reset')?'idle':'running';data.planner_source='Algorithmic';data.energy_diagnostics.adaptive=payload.mode==='adaptive'}
 else if(req.url==='/api/command'){const statuses={pause:'paused',resume:'running',return:'returning',stop:'stopped'};data.state.status=statuses[payload.command]||data.state.status}
 res.end(JSON.stringify(data.state));return;
 }
 res.statusCode=404;res.end('{}');
 });
});
server.on('upgrade',(req,socket)=>{if(req.url!=='/api/telemetry'){socket.destroy();return}const key=req.headers['sec-websocket-key'];const accept=createHash('sha1').update(key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest('base64');socket.write(`HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ${accept}\r\n\r\n`);peers.add(socket);socket.on('error',()=>peers.delete(socket));socket.on('close',()=>peers.delete(socket));socket.on('data',chunk=>{if((chunk[0]&15)===8){socket.end(Buffer.from([0x88,0]));peers.delete(socket)}});socket.write(frame(data))});
setInterval(()=>{for(const peer of peers)peer.write(frame(data))},250).unref();
server.listen(8000,'127.0.0.1',()=>console.log('TEST FIXTURE ONLY: http://127.0.0.1:8000 (synthetic public API)'));
