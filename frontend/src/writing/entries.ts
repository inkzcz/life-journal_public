import {Marked} from 'marked'
import {newId} from '../ids'
export const entryNames={l:'地点',f:'美食',m:'电影',s:'演出',g:'礼物',t:'交通'} as const
export type EntryKind=keyof typeof entryNames
export type Entry={id:string;kind:EntryKind;name:string;fields:Record<string,string>;media_ids:string[]}
export const entryMarker=':::lj-entry-v1'
export function blankEntry(kind:EntryKind='m'):Entry{return {id:newId(),kind,name:'',fields:{},media_ids:[]}}
export function validEntry(v:any):v is Entry{return !!v&&typeof v==='object'&&!Object.keys(v).some(k=>!['id','kind','name','fields','media_ids'].includes(k))&&/^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(v.id)&&typeof v.kind==='string'&&Object.hasOwn(entryNames,v.kind)&&typeof v.name==='string'&&v.name.length<=200&&!!v.name.trim()&&v.fields&&typeof v.fields==='object'&&!Array.isArray(v.fields)&&Object.values(v.fields).every(x=>typeof x==='string'&&x.length<=4000)&&Array.isArray(v.media_ids)&&v.media_ids.length<=100&&v.media_ids.every((m:unknown)=>typeof m==='string'&&/^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(m))}
export function serializeEntry(v:Entry){return `${entryMarker}\n${JSON.stringify(v)}\n:::`}
export function readEntry(src:string){const match=/^:::lj-entry-v1\r?\n([^\r\n]*)\r?\n:::(?:\r?\n|$)/.exec(src);if(!match)return null;try{const attrs=JSON.parse(match[1]!);return validEntry(attrs)?{raw:match[0],attrs:attrs as Entry}:null}catch{return null}}
export const entryFields:Record<EntryKind,[string,string,string?][]>= {
 l:[['date','到访日期','date'],['region','地区'],['city','城市'],['address','地址'],['description','地点描述'],['review','个人感受']],
 f:[['date','用餐日期','date'],['restaurant_location','餐厅地点'],['rating','评分'],['rating_scale','评分满分（明确量纲后填写）'],['price_per_person','人均价格'],['currency','币种'],['meal_period','用餐时段'],['review','美食评价']],
 m:[['original_title','原文片名'],['release_year','上映年份'],['rating_scale','评分满分（历史评分不自动转换）'],['date','观影日期','date'],['time','观影时间','time'],['cinema','影院'],['screen','影厅 / 场次'],['rating','评分'],['review','评价']],
 s:[['show_type','演出类型'],['performer','艺人 / 演出者'],['date','演出日期','date'],['time','演出时间','time'],['venue','场馆'],['seat','座位'],['ticket_tier','票档'],['end_time','结束时间','time'],['review','观演感受']],
 g:[['direction','送出 / 收到'],['person','相关人物'],['date','日期','date'],['occasion','场合'],['description','描述与回忆']],
 t:[['transport_type','交通类型（飞机 / 高铁 / 动车 / 火车 / 其他）'],['departure','出发地'],['destination','目的地'],['departure_at','出发日期时间（含UTC偏移，如2026-11-13T08:00+08:00）'],['departure_zone','出发时区（如Asia/Shanghai）'],['arrival_at','到达日期时间（含UTC偏移）'],['arrival_zone','到达时区（如Asia/Tokyo）'],['departure_station','出发机场 / 车站'],['arrival_station','到达机场 / 车站'],['terminal','航站楼'],['carriage','车厢'],['service_number','独立航班号 / 车次（可选）'],['seat','座位'],['cabin','舱位 / 席别'],['description','备注']]
}

// Marked normalizes CRLF; retain an explicit map back to original byte-preserving JS offsets.
export function entryBlocks(source:string){let normalized='',positions:number[]=[];for(let i=0;i<source.length;i++){positions.push(i);if(source[i]==='\r'&&source[i+1]==='\n'){normalized+='\n';i++}else normalized+=source[i]}positions.push(source.length)
 const p=new Marked({extensions:[{name:'lifeEntry',level:'block',start:s=>s.indexOf(entryMarker),tokenizer(src){const b=readEntry(src);if(b)return {type:'lifeEntry',raw:b.raw,attrs:b.attrs}}}]});let offset=0
 return p.lexer(normalized).map(t=>{const at=positions[offset]!,end=positions[offset+t.raw.length]!;offset+=t.raw.length;return {at,raw:source.slice(at,end),entry:t.type==='lifeEntry'?t.attrs as Entry:undefined,type:t.type}})
}
export function entryLocations(source:string){return entryBlocks(source).filter((b):b is typeof b&{entry:Entry}=>!!b.entry)}
export function sourceCardChange(source:string,id:string,operation:'duplicate'|'delete'|'up'|'down'){
 const blocks=entryBlocks(source),index=blocks.findIndex(b=>b.entry?.id===id);if(index<0)throw new Error('卡片位置已变化，请重新读取')
 const card=blocks[index]!
 if(operation==='delete')return source.slice(0,card.at)+source.slice(card.at+card.raw.length)
 if(operation==='duplicate'){const copy=JSON.parse(JSON.stringify(card.entry)) as Entry;copy.id=newId();const newline=source.includes('\r\n')?'\r\n':'\n';const raw=serializeEntry(copy).replace(/\n/g,newline);return source.slice(0,card.at+card.raw.length)+newline+newline+raw+newline+newline+source.slice(card.at+card.raw.length)}
 let neighbor=index+(operation==='up'?-1:1);while(blocks[neighbor]?.type==='space')neighbor+=operation==='up'?-1:1
 const other=blocks[neighbor];if(!other)return source
 const first=operation==='up'?other:card,last=operation==='up'?card:other,gap=source.slice(first.at+first.raw.length,last.at)
 // Preserve each block verbatim, ensuring a separator when a final block lacked a trailing LF.
 const sep=(source.includes('\r\n')?'\r\n':'\n').repeat(2)
 const between=(text:string)=>text+(text.endsWith('\n')?'':sep)
 return source.slice(0,first.at)+between(last.raw)+gap+between(first.raw)+source.slice(last.at+last.raw.length)
}
