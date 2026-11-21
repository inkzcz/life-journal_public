import {Marked} from 'marked'
import {newId} from '../ids'
export const entryNames={l:'地点',f:'美食',m:'电影',s:'演出',g:'礼物',t:'交通'} as const
export type EntryKind=keyof typeof entryNames
export type Entry={id:string;kind:EntryKind;name:string;fields:Record<string,string>;media_ids:string[]}
export const entryMarker=':::lj-entry-v1'
export function blankEntry(kind:EntryKind='m'):Entry{return {id:newId(),kind,name:'',fields:{},media_ids:[]}}
export function validEntry(v:any):v is Entry{return !!v&&typeof v==='object'&&!Object.keys(v).some(k=>!['id','kind','name','fields','media_ids'].includes(k))&&/^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(v.id)&&typeof v.kind==='string'&&Object.hasOwn(entryNames,v.kind)&&typeof v.name==='string'&&v.name.length<=200&&!!v.name.trim()&&v.fields&&typeof v.fields==='object'&&!Array.isArray(v.fields)&&Object.values(v.fields).every(x=>typeof x==='string'&&x.length<=4000)&&Array.isArray(v.media_ids)&&v.media_ids.length<=100&&v.media_ids.every((m:unknown)=>typeof m==='string'&&/^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(m))}
export function serializeEntry(v:Entry){return `${entryMarker}\n${JSON.stringify(v)}\n:::`}
export function readEntry(src:string){const match=/^:::lj-entry-v1\r?\n([^\r\n]*)\r?\n:::(?:\n|$)/.exec(src);if(!match)return null;try{const attrs=JSON.parse(match[1]!);return validEntry(attrs)?{raw:match[0],attrs:attrs as Entry}:null}catch{return null}}
export const entryFields:Record<EntryKind,[string,string,string?][]>= {
 l:[],
 f:[['date','用餐日期','date'],['review','美食评价']],
 m:[['date','观影日期','date'],['time','观影时间','time'],['cinema','影院'],['screen','影厅 / 场次'],['rating','评分'],['review','评价']],
 s:[['show_type','演出类型'],['performer','艺人 / 演出者'],['date','演出日期','date'],['time','演出时间','time'],['venue','场馆'],['seat','座位'],['review','观演感受']],
 g:[['direction','送出 / 收到'],['person','相关人物'],['date','日期','date'],['occasion','场合'],['description','描述与回忆']],
 t:[['transport_type','交通类型（飞机 / 高铁 / 动车 / 火车 / 其他）'],['departure','出发地'],['destination','目的地'],['departure_at','出发日期时间（含UTC偏移，如2026-11-13T08:00+08:00）'],['departure_zone','出发时区（如Asia/Shanghai）'],['arrival_at','到达日期时间（含UTC偏移）'],['arrival_zone','到达时区（如Asia/Tokyo）'],['departure_station','出发机场 / 车站'],['arrival_station','到达机场 / 车站'],['terminal','航站楼'],['seat','座位'],['cabin','舱位 / 席别'],['description','备注']]
}

export function entryLocations(source:string){const p=new Marked({extensions:[{name:'lifeEntry',level:'block',start:s=>s.indexOf(entryMarker),tokenizer(src){const b=readEntry(src);if(b)return {type:'lifeEntry',raw:b.raw,attrs:b.attrs}}}]});let offset=0;const out:{at:number;raw:string;entry:Entry}[]=[];for(const t of p.lexer(source)){if(t.type==='lifeEntry')out.push({at:offset,raw:t.raw,entry:t.attrs});offset+=t.raw.length}return out}
