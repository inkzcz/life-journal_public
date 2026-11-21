export type Kind='short_text'|'long_text'|'markdown'|'integer'|'decimal'|'date'|'select'|'multiselect'
export const kinds:Record<Kind,string>={short_text:'短文本',long_text:'长文本',markdown:'Markdown',integer:'整数',decimal:'小数',date:'日期',select:'单选',multiselect:'多选'}
export type Option={id:string;label:string;active:boolean}
export type Rules={min_length?:number;max_length?:number;min_value?:string|number;max_value?:string|number;min_date?:string;max_date?:string;max_items?:number;options?:Option[]}
export type Field={purpose?:string;id?:string;kind:Kind;name:string;description:string;position:number;searchable?:boolean;required:boolean;active:boolean;has_default:boolean;default_value:unknown;rules:Rules}
export type TypeSummary={id:string;slug:string;name:string;description:string;active:boolean;revision:number}
export type ContentType=TypeSummary & {is_food?:boolean;version:number;fields:Field[]}
export type RecordSummary={id:string;type_id:string;type_name:string;type_active:boolean;schema_version:number;current_type_version:number;title:string;display_date:string;status:'draft'|'published';revision:number}
export type ContentRecord=RecordSummary & {tags?:{id:string;name:string}[];summary?:string;body:string;body_format?:number;values:Record<string,unknown>;fields:Field[]}
export function clone<T>(value:T):T{return JSON.parse(JSON.stringify(value))}
export function newField():Field{return {kind:'short_text',name:'',description:'',position:0,required:false,active:true,has_default:false,default_value:null,rules:{}}}
export function initialValues(fields:Field[],existing:Record<string,unknown>={}):Record<string,unknown>{
  const result:Record<string,unknown>={...existing}
  for(const field of fields){if(field.id && field.active && !(field.id in result))result[field.id]=field.has_default?clone(field.default_value):null}
  return result
}
export function fieldPayload(fields:Field[]):Field[]{
  return fields.map((f,index)=>{
    const rules=Object.fromEntries(Object.entries(f.rules).filter(([,v])=>v!==''&&v!==null&&v!==undefined)) as Rules
    return {...clone(f),position:index,default_value:f.has_default?f.default_value:null,rules}
  })
}
