import {useEffect,useRef,useState} from 'react';
import type {Cost,Grid,Point,Telemetry} from '../types.ts';
import {BASE,costAt,fitMap,heatColor,occupancyColor,rasterOffset,scaleLength,screenPath,screenToWorld,worldToScreen,type View} from '../mapMath.ts';
import {useI18n} from '../i18n/index.tsx';
export function WorldMap({data,grid,online,presentation,onInspect}:{data:Telemetry|null;grid:Grid|null;online:boolean;presentation:boolean;onInspect:(cost:Cost)=>void}) {
 const {t,n}=useI18n();
 const canvas=useRef<HTMLCanvasElement>(null),raster=useRef<HTMLCanvasElement|null>(null);
 const [size,setSize]=useState({w:800,h:560});
 const [view,setView]=useState<View>({x:-2,y:-.5,zoom:80}),[follow,setFollow]=useState(false),[pointer,setPointer]=useState<Point|null>(null);
 const [layers,setLayers]=useState({path:true,visited:true,costs:true});
 const drag=useRef<{x:number;y:number;view:View}|null>(null), fitted=useRef<number|null>(null),automaticFit=useRef(true);
 const currentView=follow&&data?.robot_pose?{...view,...data.robot_pose}:view;
 useEffect(()=>{const c=canvas.current;if(!c)return;const observer=new ResizeObserver(()=>{const r=c.getBoundingClientRect();setSize({w:r.width,h:r.height})});observer.observe(c);return()=>observer.disconnect()},[]);
 useEffect(()=>{if(!grid){raster.current=null;fitted.current=null;automaticFit.current=true;return}const c=document.createElement('canvas');c.width=grid.width;c.height=grid.height;const ctx=c.getContext('2d');if(!ctx)return;const image=ctx.createImageData(c.width,c.height);
 grid.data.forEach((value,i)=>{const j=rasterOffset(i,grid.width,grid.height);image.data.set([...occupancyColor(value),255],j)});ctx.putImageData(image,0,0);raster.current=c;
 },[grid]);
 useEffect(()=>{if(grid&&(fitted.current!==grid.revision||automaticFit.current)){setView(fitMap(grid,size.w,size.h));fitted.current=grid.revision}},[grid,size]);
 useEffect(()=>{const c=canvas.current;if(!c)return;const ctx=c.getContext('2d');if(!ctx)return;
 const {w,h}=size,dpr=window.devicePixelRatio||1;
 c.width=Math.round(w*dpr);c.height=Math.round(h*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);
 const v=currentView,z=v.zoom,px=(p:Point)=>worldToScreen(p,v,w,h);
 ctx.fillStyle='#0b151e';ctx.fillRect(0,0,w,h);ctx.strokeStyle='#1b2c39';ctx.lineWidth=.6;
 const step=z<30?5:1;
 for(let x=Math.floor((v.x-w/2/z)/step)*step;x<v.x+w/2/z;x+=step){const q=px({x,y:0});ctx.beginPath();ctx.moveTo(q.x,0);ctx.lineTo(q.x,h);ctx.stroke()}
 for(let y=Math.floor((v.y-h/2/z)/step)*step;y<v.y+h/2/z;y+=step){const q=px({x:0,y});ctx.beginPath();ctx.moveTo(0,q.y);ctx.lineTo(w,q.y);ctx.stroke()}
 if(grid&&raster.current){const o=px(grid.origin);ctx.save();ctx.translate(o.x,o.y);ctx.rotate(-grid.origin_yaw);ctx.imageSmoothingEnabled=false;ctx.drawImage(raster.current,0,-grid.height*grid.resolution*z,grid.width*grid.resolution*z,grid.height*grid.resolution*z);ctx.restore()}
 const measured=(data?.knowledge||[]).filter(e=>e.move_samples>0),min=Math.min(...measured.map(e=>e.energy_per_m)),max=Math.max(...measured.map(e=>e.energy_per_m));
 if(layers.costs)(data?.knowledge||[]).forEach(e=>{const p=px(e.cell),cell=.5*z;ctx.save();ctx.translate(p.x,p.y);ctx.rotate(-(grid?.origin_yaw??0));ctx.fillStyle=e.move_samples?heatColor(e.energy_per_m,min,max):'#94a3b8';ctx.globalAlpha=e.move_samples?.48:.08;ctx.fillRect(-cell/2,-cell/2,cell,cell);ctx.globalAlpha=.7;ctx.strokeStyle=e.move_samples?heatColor(e.energy_per_m,min,max):'#8693a1';ctx.setLineDash(e.move_samples?[]:[2,3]);ctx.strokeRect(-cell/2,-cell/2,cell,cell);ctx.restore()});
 const line=(points:Point[],color:string,width:number,dash:number[])=>{const path=screenPath(points,v,w,h);if(!path.length)return;ctx.beginPath();path.forEach((p,i)=>i?ctx.lineTo(p.x,p.y):ctx.moveTo(p.x,p.y));ctx.lineJoin='round';ctx.lineCap='round';ctx.strokeStyle=color;ctx.lineWidth=width;ctx.setLineDash(dash);ctx.stroke();ctx.setLineDash([])};
 if(layers.visited)line(data?.trajectory||[],'#65dcb7',presentation?4:2.5,[]);
 if(layers.path){line(data?.planned_path||[],'#090f1b',presentation?7:5,[]);line(data?.planned_path||[],'#b7b3fc',presentation?3:2,[7,6])}
 const home=px(BASE);ctx.fillStyle='#132f30';ctx.strokeStyle='#70ddc0';ctx.lineWidth=2;ctx.beginPath();ctx.arc(home.x,home.y,14,0,Math.PI*2);ctx.fill();ctx.stroke();ctx.fillStyle='#8befd1';ctx.font='bold 15px sans-serif';ctx.textAlign='center';ctx.fillText('⌂',home.x,home.y+5);ctx.font='12px sans-serif';ctx.textAlign='left';ctx.fillText(t('map.base'),home.x+20,home.y+4);
 (data?.collected_positions||[]).forEach(p=>{const q=px(p);ctx.fillStyle='#f5c873';ctx.strokeStyle='#392b16';ctx.lineWidth=2;ctx.beginPath();ctx.arc(q.x,q.y,6,0,Math.PI*2);ctx.fill();ctx.stroke()});
 const goal=data?.state.goal?.target;if(goal){const q=px(goal);ctx.strokeStyle='#c8c2ff';ctx.lineWidth=2;ctx.beginPath();ctx.arc(q.x,q.y,10,0,Math.PI*2);ctx.moveTo(q.x-16,q.y);ctx.lineTo(q.x+16,q.y);ctx.moveTo(q.x,q.y-16);ctx.lineTo(q.x,q.y+16);ctx.stroke()}
 if(data?.robot_pose){const p=px(data.robot_pose),s=presentation?1.4:1;ctx.save();ctx.translate(p.x,p.y);ctx.rotate(-data.robot_yaw);ctx.scale(s,s);
 ctx.fillStyle=online?'#6ce1c3':'#91a0b1';ctx.strokeStyle='#10282b';ctx.lineWidth=2;ctx.beginPath();ctx.arc(0,0,11,0,Math.PI*2);ctx.fill();ctx.stroke();ctx.fillStyle='#0f2930';ctx.fillRect(-7,-13,10,4);ctx.fillRect(-7,9,10,4);ctx.beginPath();ctx.arc(-3,0,4,0,Math.PI*2);ctx.fill();ctx.fillStyle=online?'#caffec':'#d3d9e0';ctx.beginPath();ctx.moveTo(25,0);ctx.lineTo(14,-5);ctx.lineTo(14,5);ctx.closePath();ctx.fill();ctx.restore();}
 const scale=scaleLength(z),length=scale*z;ctx.strokeStyle='#dae4ec';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(w-24-length,h-25);ctx.lineTo(w-24,h-25);ctx.stroke();ctx.font='11px sans-serif';ctx.textAlign='right';ctx.fillStyle='#c9d8e3';ctx.fillText(t('map.scale',{value:n(scale,scale<1?2:0)}),w-24,h-36);
 },[data,grid,size,currentView.x,currentView.y,currentView.zoom,layers,online,presentation,t,n]);
 const reset=()=>{automaticFit.current=true;setFollow(false);setView(fitMap(grid,size.w,size.h))};
 const zoom=(factor:number,anchor?:Point)=>{automaticFit.current=false;const v=currentView,next={...v,zoom:Math.max(8,Math.min(600,v.zoom*factor))};if(anchor){const before=screenToWorld(anchor,v,size.w,size.h),after=screenToWorld(anchor,next,size.w,size.h);next.x+=before.x-after.x;next.y+=before.y-after.y;setFollow(false)}setView(next)};
 const readings=(data?.knowledge||[]).filter(e=>e.move_samples>0);
 const range={min:Math.min(...readings.map(e=>e.energy_per_m)),max:Math.max(...readings.map(e=>e.energy_per_m))};
 const hovered=pointer&&layers.costs?costAt(pointer,data?.knowledge||[],grid?.origin_yaw??0):undefined;
 return <div className="map-area"><canvas ref={canvas} tabIndex={0} aria-label={t('map.canvas')} onKeyDown={e=>{const delta=40/currentView.zoom;const offsets:Record<string,Point>={ArrowLeft:{x:-delta,y:0},ArrowRight:{x:delta,y:0},ArrowUp:{x:0,y:delta},ArrowDown:{x:0,y:-delta}};if(offsets[e.key]){e.preventDefault();automaticFit.current=false;setFollow(false);setView({...currentView,x:currentView.x+offsets[e.key].x,y:currentView.y+offsets[e.key].y})}else if(e.key==='+'||e.key==='='){e.preventDefault();zoom(1.2)}else if(e.key==='-'){e.preventDefault();zoom(1/1.2)}else if(e.key==='Home'){e.preventDefault();reset()}}} onWheel={e=>{e.preventDefault();const r=e.currentTarget.getBoundingClientRect();zoom(Math.exp(-e.deltaY*.001),{x:e.clientX-r.left,y:e.clientY-r.top})}} onPointerDown={e=>{automaticFit.current=false;e.currentTarget.setPointerCapture(e.pointerId);drag.current={x:e.clientX,y:e.clientY,view:currentView};setView(currentView);setFollow(false)}} onPointerUp={()=>{drag.current=null;if(hovered)onInspect(hovered)}} onPointerCancel={()=>{drag.current=null}} onPointerLeave={()=>setPointer(null)} onPointerMove={e=>{const r=e.currentTarget.getBoundingClientRect();setPointer(screenToWorld({x:e.clientX-r.left,y:e.clientY-r.top},currentView,size.w,size.h));const d=drag.current;if(d)setView({...d.view,x:d.view.x-(e.clientX-d.x)/d.view.zoom,y:d.view.y+(e.clientY-d.y)/d.view.zoom})}}/>
 <div className="map-tools"><button title={t('map.zoomIn')} aria-label={t('map.zoomIn')} onClick={()=>zoom(1.2)}>+</button><button title={t('map.zoomOut')} aria-label={t('map.zoomOut')} onClick={()=>zoom(1/1.2)}>−</button><button aria-label={t('map.reset')} title={t('map.reset')} onClick={reset}>⊞ <span>{t('map.reset')}</span></button><button aria-label={t('map.follow')} aria-pressed={follow} className={follow?'selected':''} onClick={()=>{automaticFit.current=false;setView(currentView);setFollow(!follow)}}>◎ <span>{t('map.follow')}</span></button></div>
 <div className="map-layers">{(['path','visited','costs'] as const).map(k=><label key={k}><input type="checkbox" checked={layers[k]} onChange={()=>setLayers(v=>({...v,[k]:!v[k]}))}/>{t(`map.${k}`)}</label>)}</div>
 <div className="map-frame">{t('map.frame')}</div>
 {layers.costs&&readings.length>0&&<div className="map-heat-scale"><span>{t('energy.unit')}</span><div className="heat-gradient" style={range.min===range.max?{background:heatColor(range.min,range.min,range.max)}:undefined}/><div className="scale-labels"><span>{n(range.min,2)}</span><span>{n(range.max,2)}</span></div></div>}
 {hovered&&<div className="map-tooltip" role="status"><strong>{t(hovered.move_samples?'energy.measured':'energy.prior')}</strong><span>{n(hovered.energy_per_m,2)} {t('energy.unit')}</span><span>{t('energy.samples',{count:n(hovered.move_samples||0,0)})}</span><span>{hovered.uncertainty==null?t('energy.unknown'):t('energy.uncertainty',{value:n(hovered.uncertainty,3)})}</span></div>}
 <div className="map-bottom"><div className="legend">{(['robot','path','visited','base','samples','wall','free','unknown'] as const).map(k=><span key={k}><i className={`legend-mark ${k}`}/>{t(`map.${k}`)}</span>)}{layers.costs&&<><span><i className="legend-mark measured"/>{t('energy.measured')}</span><span><i className="legend-mark prior"/>{t('energy.prior')}</span></>}</div><div className="cursor">{pointer?t('map.position',{x:n(pointer.x,2),y:n(pointer.y,2)}):t('map.hint')}</div></div>
 {!online&&<div className="map-offline"><strong>{data?t('map.stale'):t('map.wait')}</strong><small>{t('map.noMotion')}</small></div>}
 </div>;
}
