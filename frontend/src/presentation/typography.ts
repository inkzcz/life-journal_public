import {ref} from 'vue'
import {request} from '../api'
export type Typography={editor_line:number;editor_gap:number;reader_line:number|null;reader_gap:number|null;revision:number}
export const defaults=():Typography=>({editor_line:1.5,editor_gap:8,reader_line:null,reader_gap:null,revision:0})
export const saved=ref<Typography>(defaults())
let loaded=false,pending:Promise<void>|undefined
export function apply(value:Typography){for(const [key,v] of Object.entries(value)){if(key==='revision')continue;const name='--lj-'+key.replace('_','-');if(v==null)document.documentElement.style.removeProperty(name);else if(Number.isFinite(v))document.documentElement.style.setProperty(name,String(v)+(key.endsWith('gap')?'px':''))}}
export function loadTypography(force=false){if(pending)return pending;if(loaded&&!force)return Promise.resolve();if(!pending)pending=request('/blog/typography').then(d=>{if(d&&[1,1.25,1.5,1.75,2].includes(d.editor_line)){saved.value=d;apply(d);loaded=true}}).catch(()=>{/* reading retains old safe defaults when preferences cannot be read */}).finally(()=>pending=undefined);return pending}
