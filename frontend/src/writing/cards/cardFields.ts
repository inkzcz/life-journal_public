import {entryFields,type Entry} from '../entries'
export function extras(entry:Entry,used:string[]){const known=new Map(Object.values(entryFields).flat().map(([key,label])=>[key,label]));return Object.entries(entry.fields).filter(([key,value])=>!used.includes(key)&&key!=='place_id'&&!!value.trim()).map(([key,value])=>({key,label:known.get(key)||key,value}))}
export const notes=['review','description']
