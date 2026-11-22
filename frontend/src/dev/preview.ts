// Original development-only fixture. Never imported by the production entry.
import {createApp,h} from 'vue'
import {createRouter,createMemoryHistory,RouterView} from 'vue-router'
import {blankSite} from '../blog/types'
import {installAppearance,activeAppearance} from '../ui/theme'
import Preview from './WritingPreview.vue'
import '../ui/tokens.css'
import '../blog/themes.css'
import '../style.css'
import '../ui/reader.css'
import '../ui/studio.css'
import '../ui/editor.css'
import '../blog/personalization.css'
import '../presentation/typography.css'
import '../ui/modern.css'
import '../blog/modern-soft.css'
import '../blog/appearance.css'
import '../ui/system.css'

if(!import.meta.env.DEV)throw Error('Synthetic preview is development-only')
const base={id:'11111111-1111-4111-8111-111111111111',slug:'life-journal-article',name:'文章',description:'合成基础类型',active:true,revision:1,version:1,fields:[]}
const records=new Map<string,any>()
let configuration={enabled:false,url_template:'https://wxpusher.zjiecode.com/api/send/message/SPT_SYNTHETIC_ONLY/{content}?title={title}',timezone:'Asia/Shanghai',time:'09:00',expected_revision:0}
const picture='<svg xmlns="http://www.w3.org/2000/svg" width="960" height="640" viewBox="0 0 960 640"><rect width="960" height="640" fill="#e6ede7"/><circle cx="720" cy="155" r="60" fill="#d8bc85"/><path d="M0 560 300 180 600 640H0" fill="#9eafa0"/><path d="m350 640 320-330 290 250v80" fill="#668472"/><text x="40" y="600" font-family="sans-serif" font-size="24" fill="#fff">合成验收素材 · 无私人照片</text></svg>'
function json(value:unknown){return new Response(JSON.stringify(value),{headers:{'Content-Type':'application/json','Cache-Control':'no-store'}})}
window.fetch=async(input,options={})=>{
 const raw=typeof input==='string'?input:input instanceof URL?input.toString():input.url
 const url=new URL(raw,location.origin),path=url.pathname,method=(options.method||'GET').toUpperCase()
 // Fail closed: no real API, external URL or private content is ever fetched.
 if(url.origin!==location.origin||!path.startsWith('/api/'))throw Error('Synthetic preview refuses network access')
 if(path==='/api/auth/csrf')return json({csrf_token:'synthetic-preview-only'})
 if(path==='/api/blog/site')return json({...blankSite(),appearance:activeAppearance.value})
 if(path==='/api/admin/status')return json({is_admin:true})
 if(path==='/api/admin/content/types')return json([base])
 if(path==='/api/admin/templates')return json([])
 if(path==='/api/admin/content/types/default-article'||path==='/api/admin/content/types/'+base.id)return json(base)
 if(path==='/api/admin/content/records'&&method==='GET')return json({items:[...records.values()].map(r=>({...r,type_name:'文章'})),total:records.size})
 if(path.startsWith('/api/admin/content/records')){
  const id=path.split('/')[5]||'33333333-3333-4333-8333-333333333333'
  if(method==='GET')return json(records.get(id)||{})
  const data=JSON.parse(String(options.body)),record={...data,id,type_id:data.type_id||base.id,type_active:true,current_type_version:1,fields:[],revision:(records.get(id)?.revision||0)+1,connections:{...data.connections,incoming:[]}}
  records.set(id,record);return json(record)
 }
 if(path.startsWith('/api/calendar'))return json({items:[],today:'2026-11-22'})
 if(path==='/api/admin/calendar/events'||path==='/api/admin/calendar/logs')return json([])
 if(path==='/api/admin/calendar/notification'){
  if(method==='PUT')configuration={...JSON.parse(String(options.body)),expected_revision:configuration.expected_revision+1}
  return json(configuration)
 }
 if(path==='/api/admin/calendar/notification/test')return json({state:'synthetic-only',note:'合成预览不会发送通知'})
 if(path.startsWith('/api/library-media/'))return new Response(picture,{headers:{'Content-Type':'image/svg+xml','Cache-Control':'no-store'}})
 return new Response(JSON.stringify({detail:'合成预览未实现此操作，不会访问真实服务'}),{status:404,headers:{'Content-Type':'application/json'}})
}
const router=createRouter({history:createMemoryHistory(),routes:[{path:'/:pathMatch(.*)*',component:Preview}]})
installAppearance()
createApp({render:()=>h(RouterView)}).use(router).mount('#app')
