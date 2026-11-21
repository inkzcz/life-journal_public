import type { Field } from '../admin/types'
export const moduleKinds={header:'标题与封面',summary:'信息摘要',body:'故事正文',fields:'字段信息卡',gallery:'照片画廊',timeline:'日期时间线',related:'相关记录与地点',itinerary:'逐日旅行行程',map:'私人地点地图',album:'增强相册',life_timeline:'关联生活时间线'}
export type DisplayModule={id:string;kind:keyof typeof moduleKinds;title:string;enabled:boolean;layout:'grid'|'masonry'|'large'|'card'|'date';field_ids:string[];group_by?:'none'|'manual'|'date'|'place'}
export type TemplateField=Field & {key?:string;group?:string}
export type TemplateDraft={id?:string;slug:string;name:string;description:string;active:boolean;revision?:number;expected_type_revision?:number;version?:number;type_id?:string;schema_version?:number;fields:TemplateField[];modules:DisplayModule[]}
export function fromServer(t:any):TemplateDraft{return {...t,fields:t.fields.map((f:any)=>({...f.field,key:f.key,group:f.group}))}}
export function formGroups(fields:Field[],config?:{form:{id:string;group:string}[]}){
 const groups:{name:string;fields:Field[]}[]=[]
 for(const f of fields){const name=config?.form.find(x=>x.id===f.id)?.group||'基本信息';let g=groups.find(x=>x.name===name);if(!g){g={name,fields:[]};groups.push(g)}g.fields.push(f)}
 return groups
}
