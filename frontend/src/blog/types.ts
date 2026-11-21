import type { ColorOverrides,CombinationColors } from './colors'
export type Style='modern-flat'|'editorial'|'modern-soft'|'glass'
export type PaletteName='celadon'|'lilac'
export const styles={'modern-flat':'Modern Flat',editorial:'Editorial','modern-soft':'Modern Soft',glass:'Glass'}
export const palettes={celadon:'晨雾青瓷',lilac:'丁香奶油'}
export type Appearance={theme:'modern'|'default'|'editorial'|'soft'|'glass'|'celadon';style?:Style|null;palette?:PaletteName|null;combination_colors?:CombinationColors;mode:'light'|'dark'|'system';revision?:number;colors?:ColorOverrides}
export const layouts={feature:'大图精选',grid2:'双列卡片',grid3:'三列网格',list:'简洁列表'}
export type Section={id:string;name:string;slug:string;description:string;cover_id:string|null;active:boolean;position:number;layout:keyof typeof layouts;type_ids:string[];revision:number}
export type Nav={id:string;name:string;kind:'home'|'section'|'record'|'page';parent_id:string|null;section_id:string|null;record_id:string|null;page:'journals'|'sections'|'stories'|'about'|'food'|'movies'|'shows'|'gifts'|'transport'|'photos'|'calendar'|'trips'|'places'|null;active:boolean}
export type Post={id:string;title:string;display_date:string;type_name:string;excerpt:string;cover:{id:string;alt:string;caption:string}|null}
export type Module={id:string;kind:'hero'|'featured'|'latest'|'section'|'gallery'|'text'|'anniversary_calendar';horizon?:number;show_countdown?:boolean;show_years?:boolean;events?:any[];enabled:boolean;title:string;text:string;count:number;layout:keyof typeof layouts;section_id:string|null;type_id:string|null;record_ids:string[];items?:Post[]}
export type Home={title:string;description:string;modules:Module[];revision?:number}
export type ResolvedHome=Omit<Home,'modules'> & {modules:Omit<Module,'record_ids'|'section_id'|'type_id'>[]}
export type Site={title:string;description:string;appearance:Appearance;navigation:Nav[];sections:Section[]}
export const blankSite=():Site=>({title:'Life Journal',description:'',appearance:{theme:'celadon',style:'modern-soft',palette:'celadon',mode:'system'},navigation:[],sections:[]})
export function navPath(n:Nav,sections:Section[]){if(n.kind==='home')return '/';if(n.kind==='record')return '/posts/'+n.record_id;if(n.kind==='section'){const s=sections.find(s=>s.id===n.section_id);return s?'/sections/'+s.slug:'/sections'}const pages:Record<string,string>={food:'/food',movies:'/experiences/m',shows:'/experiences/s',gifts:'/experiences/g',transport:'/experiences/t',photos:'/photos',calendar:'/calendar',trips:'/trips',places:'/places'};if(n.page&&pages[n.page])return pages[n.page]!;return n.page==='about'?'/about':n.page==='journals'?'/stories':n.page==='stories'?'/stories':'/sections'}
export function fieldDisplay(field:any,value:unknown){if(value==null||value===''||(Array.isArray(value)&&!value.length))return '';if(field.kind==='select'||field.kind==='multiselect')return (Array.isArray(value)?value:[value]).map(v=>field.rules.options?.find((o:any)=>o.id===v)?.label||'已失效选项').join('、');if(typeof value==='boolean')return value?'是':'否';return String(value)}
