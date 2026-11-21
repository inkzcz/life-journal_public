export type Activity={experience_id?:string|null;kind?:'food'|'sight'|'transport'|'other';dish?:string;price?:string|null;currency?:string;rating?:number|null;experience?:string;source_key?:string|null;id:string;day:string;time:string|null;title:string;description:string;place_id:string|null;media_ids:string[]}
export type PhotoNote={media_id:string;taken_on:string|null;place_id:string|null;group_name:string}
export type Life={start_date:string|null;end_date:string|null;map_mode:'offline'|'hidden';activities:Activity[];photos:PhotoNote[]}
export function emptyLife():Life{return {start_date:null,end_date:null,map_mode:'offline',activities:[],photos:[]}}
export function lifePayload(life:Life):Life{return {...life,start_date:life.start_date||null,end_date:life.end_date||null,activities:life.activities.map(a=>({...a,...(a.price===''?{price:null}:{}),time:a.time||null,place_id:a.place_id||null})),photos:life.photos.map(p=>({...p,taken_on:p.taken_on||null,place_id:p.place_id||null}))}}
export function groupedDays(activities:Activity[]){const days=[...new Set(activities.map(a=>a.day))].sort();return days.map(day=>({day,items:activities.filter(a=>a.day===day)}))}
export function projectPlaces(places:any[]){
 const valid=places.filter(p=>p.latitude!=null&&p.longitude!=null&&Number.isFinite(Number(p.latitude))&&Number.isFinite(Number(p.longitude)))
 if(!valid.length)return []
 const anchor=Number(valid[0].longitude),coords=valid.map(p=>{let x=Number(p.longitude);while(x-anchor>180)x-=360;while(x-anchor< -180)x+=360;return {p,x,y:Number(p.latitude)}})
 const xs=coords.map(p=>p.x),ys=coords.map(p=>p.y),minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys)
 return coords.map(({p,x,y})=>({...p,x:maxX===minX?400:60+(x-minX)/(maxX-minX)*680,y:maxY===minY?200:340-(y-minY)/(maxY-minY)*280}))
}
export function photoGroups(photos:any[],notes:PhotoNote[]=[],places:any[]=[],by='none'){
 const groups:{name:string;photos:any[]}[]=[]
 for(const p of photos){const n=notes.find(n=>n.media_id===p.id);const name=by==='date'?(n?.taken_on||'日期未指定'):by==='place'?(places.find(p=>p.id===n?.place_id)?.name||'地点未指定'):by==='manual'?(n?.group_name||'未分组'):'';let group=groups.find(g=>g.name===name);if(!group){group={name,photos:[]};groups.push(group)}group.photos.push(p)}
 if(by==='date')groups.sort((a,b)=>a.name.localeCompare(b.name));return groups
}
