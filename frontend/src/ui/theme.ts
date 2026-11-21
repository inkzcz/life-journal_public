import {computed,ref,watch} from 'vue'
import {request} from '../api'
import {blankSite,type Appearance,type Style,type PaletteName} from '../blog/types'
import {appearanceAttrs,colorLabels,colorStyle,customKeys,isHex} from '../blog/colors'
const themes=['modern','default','editorial','soft','glass','celadon'],styles=['modern-flat','editorial','modern-soft','glass'],palettes=['celadon','lilac'],modes=['light','dark','system']
export const APPEARANCE_CACHE='life-journal.appearance.v1'
// Cache ONLY finite appearance values. Never cache site text, records, identity or credentials.
export function sanitizeAppearance(value:unknown):Appearance{
 const v=value&&typeof value==='object'?value as any:{}
 const a:Appearance={theme:themes.includes(v.theme)?v.theme:blankSite().appearance.theme,mode:modes.includes(v.mode)?v.mode:'system'}
 if(styles.includes(v.style))a.style=v.style
 if(palettes.includes(v.palette))a.palette=v.palette
 const clean=(p:any)=>Object.fromEntries(Object.keys(colorLabels).filter(k=>isHex(p?.[k])).map(k=>[k,p[k]]))
 if(v.colors&&typeof v.colors==='object'){a.colors={};for(const theme of themes)if(v.colors[theme]){const bank:any={};for(const mode of ['light','dark'])if(Object.hasOwn(v.colors[theme],mode))bank[mode]=clean(v.colors[theme][mode]);(a.colors as any)[theme]=bank}}
 if(v.combination_colors&&typeof v.combination_colors==='object'){a.combination_colors={};for(const style of styles)for(const palette of palettes){const vbank=v.combination_colors[style]?.[palette];if(!vbank)continue;const bank:any={};for(const mode of ['light','dark'])if(Object.hasOwn(vbank,mode))bank[mode]=clean(vbank[mode]);a.combination_colors[style as Style]??={};a.combination_colors[style as Style]![palette as PaletteName]=bank}}
 if(Number.isSafeInteger(v.revision)&&v.revision>=0)a.revision=v.revision
 return a
}
function initial(){try{const raw=localStorage.getItem(APPEARANCE_CACHE);if(raw&&raw.length<65536)return sanitizeAppearance(JSON.parse(raw))}catch{}return blankSite().appearance}
export const savedAppearance=ref<Appearance>(initial())
const preview=ref<{owner:symbol;appearance:Appearance}|null>(null)
export const activeAppearance=computed(()=>preview.value?.appearance||savedAppearance.value)
export const systemDark=ref(false)
export function displayMode(a:Appearance){return a.mode==='dark'||a.mode==='system'&&systemDark.value?'dark':'light'}
let generation=0
export function appearanceEpoch(){return generation}
export function rememberAppearance(a:Appearance,epoch?:number){if(epoch!==undefined&&epoch!==generation)return;generation++;savedAppearance.value=sanitizeAppearance(a);try{localStorage.setItem(APPEARANCE_CACHE,JSON.stringify(savedAppearance.value))}catch{/* private browsing/quota must not prevent appearance or saving */}}
export function previewAppearance(owner:symbol,a:Appearance){preview.value={owner,appearance:sanitizeAppearance(a)}}
export function cancelAppearancePreview(owner:symbol){if(preview.value?.owner===owner)preview.value=null}
export async function refreshAppearance(){const g=++generation;try{const site=await request('/blog/site');if(g===generation)rememberAppearance(site.appearance)}catch{/* Auth remains enforced by existing guards; do not expose private config. */}}
export function installAppearance(){
 const mq=window.matchMedia?.('(prefers-color-scheme: dark)');const sync=()=>{systemDark.value=!!mq?.matches};sync();mq?.addEventListener('change',sync)
 const root=document.documentElement;root.classList.add('lj-theme')
 const stop=watch([activeAppearance,systemDark],()=>{const a=activeAppearance.value,mode=displayMode(a);for(const [key,value] of Object.entries({...appearanceAttrs(a),'data-mode':mode,'data-custom':customKeys(a,mode)}))root.setAttribute(key,value);for(const key of Object.keys(colorLabels))root.style.removeProperty('--reader-'+key.replaceAll('_','-'));for(const [key,value] of Object.entries(colorStyle(a,mode)))root.style.setProperty(key,value)},{immediate:true,flush:'sync'})
 const storage=(event:StorageEvent)=>{if(event.key===APPEARANCE_CACHE&&event.newValue&&event.newValue.length<65536){try{const next=sanitizeAppearance(JSON.parse(event.newValue));generation++;savedAppearance.value=next}catch{}}};window.addEventListener('storage',storage)
 return ()=>{stop();mq?.removeEventListener('change',sync);window.removeEventListener('storage',storage)}
}
