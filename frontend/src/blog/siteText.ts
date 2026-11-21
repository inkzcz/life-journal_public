import { reactive } from 'vue'
import { request } from '../api'
const state=reactive<{site_name?:string;values:Record<string,string>;defaults:Record<string,string>}>({values:{},defaults:{}})
export function label(key:string,fallback:string){return state.values[key]||fallback||state.defaults[key]}
export async function loadText(){const d=await request('/site/text');applyText(d)}
export function applyText(d:{site_name?:string;values:Record<string,string>;defaults:Record<string,string>}){state.values=d.values;state.defaults=d.defaults;state.site_name=d.site_name}

export function siteName(){return state.site_name||'Life Journal'}
