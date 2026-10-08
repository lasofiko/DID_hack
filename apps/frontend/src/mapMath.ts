import type {Cost, Grid, Point} from './types.ts';
export const BASE: Point = {x:-2, y:-.5}; // Public mission configuration, configs/agent.json.
export const ENERGY_CELL_SIZE = .5;
export type View = {x:number; y:number; zoom:number};
export function worldToScreen(p:Point,v:View,w:number,h:number):Point {return {x:w/2+(p.x-v.x)*v.zoom,y:h/2-(p.y-v.y)*v.zoom}}
export function screenToWorld(p:Point,v:View,w:number,h:number):Point {return {x:v.x+(p.x-w/2)/v.zoom,y:v.y-(p.y-h/2)/v.zoom}}
export function gridToWorld(p:Point,grid:Grid):Point {
 const c=Math.cos(grid.origin_yaw),s=Math.sin(grid.origin_yaw);
 return {x:grid.origin.x+c*p.x-s*p.y,y:grid.origin.y+s*p.x+c*p.y};
}
export function fitMap(grid:Grid|null,w:number,h:number):View {
 if(!grid)return {x:BASE.x,y:BASE.y,zoom:80};
 const corners=[{x:0,y:0},{x:grid.width*grid.resolution,y:0},{x:0,y:grid.height*grid.resolution},{x:grid.width*grid.resolution,y:grid.height*grid.resolution}].map(p=>gridToWorld(p,grid));
 const xs=corners.map(p=>p.x),ys=corners.map(p=>p.y);
 const left=Math.min(...xs),right=Math.max(...xs),bottom=Math.min(...ys),top=Math.max(...ys);
 return {x:(left+right)/2,y:(bottom+top)/2,zoom:Math.max(8,Math.min(400,Math.min((w-72)/(right-left),(h-150)/(top-bottom))))};
}
export function costAt(p:Point,costs:Cost[],yaw:number):Cost|undefined {
 const c=Math.cos(yaw),s=Math.sin(yaw);
 return costs.find(e=>{const x=p.x-e.cell.x,y=p.y-e.cell.y;return Math.abs(c*x+s*y)<ENERGY_CELL_SIZE/2&&Math.abs(-s*x+c*y)<ENERGY_CELL_SIZE/2});
}
// Drop only subpixel neighbours; retain endpoints and visible detail, with no fixed tail cutoff.
export function screenPath(points:Point[],v:View,w:number,h:number):Point[] {
 const result:Point[]=[];
 points.forEach((p,i)=>{const q=worldToScreen(p,v,w,h),prev=result.at(-1);if(!prev||i===points.length-1||Math.hypot(q.x-prev.x,q.y-prev.y)>=1)result.push(q)});
 return result;
}
export function scaleLength(zoom:number):number {
 const desired=85/zoom, magnitude=10**Math.floor(Math.log10(desired));
 return [1,2,5,10].map(x=>x*magnitude).find(x=>x>=desired)??magnitude;
}
export function heatColor(value:number,min:number,max:number):string {
 const ratio=max===min?.5:Math.max(0,Math.min(1,(value-min)/(max-min)));
 return `hsl(${165-145*ratio} 65% 55%)`;
}
// ROS row zero is the bottom row; canvas raster row zero is the top row.
export function rasterOffset(index:number,width:number,height:number):number {
 return ((height-1-Math.floor(index/width))*width+index%width)*4;
}
export function occupancyColor(value:number):[number,number,number] {
 return value<0?[26,37,49]:value>=50?[137,161,178]:[45,63,77];
}
