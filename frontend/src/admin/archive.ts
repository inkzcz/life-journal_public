export type Asset={captured_on?:string|null;folder_id?:string|null;category?:string;id:string;filename:string;mime_type:string;size:number;width:number;height:number;title:string;description:string;alt:string;revision:number;created_at:string;references?:RecordRef[]}
export type RecordRef={category?:'current'|'history'|'inactive'|'trash'|'system';active?:boolean;kind?:string;revision?:number;id:string;title:string;deleted:boolean;type_id:string;label?:string}
export type Place={id:string;name:string;country:string;region:string;city:string;address:string;category:string;notes:string;latitude:string|null;longitude:string|null;active:boolean;revision:number;references?:RecordRef[]}
export type Connections={media:{id:string;cover:boolean;caption:string;asset:Asset}[];links:RecordRef[];places:Place[];incoming:RecordRef[]}
export const emptyConnections=():Connections=>({media:[],links:[],places:[],incoming:[]})
export function connectionsPayload(value:Connections){return {media:value.media.map(m=>({id:m.id,cover:m.cover,caption:m.caption})),links:value.links.map(l=>({id:l.id,label:l.label})),places:value.places.map(p=>p.id)}}
