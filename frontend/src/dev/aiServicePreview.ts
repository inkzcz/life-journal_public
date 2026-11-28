// Synthetic development fixture. Never imported by the production entry.
import {createApp,h} from 'vue'
import {createRouter,createMemoryHistory,RouterView} from 'vue-router'
import {installAppearance} from '../ui/theme'
import Preview from './AIServicePreview.vue'
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
const sid='10000000-0000-4000-8000-000000000001',mid='20000000-0000-4000-8000-000000000001'
let config:any={revision:1,default_provider:mid,services:[{id:sid,name:'合成 Claude 服务商 · 可编辑区域地址',kind:'anthropic',base_url:'https://synthetic.example/v1',key_env:'LJ_AI_KEY_SYNTHETIC_REFERENCE',enabled:true,timeout_seconds:60}],providers:[{id:mid,service_id:sid,name:'合成文本与视觉模型',model:'synthetic-model',kind:'anthropic',base_url:'https://synthetic.example/v1',key_env:null,enabled:true,text:true,vision:true,reasoning:false,json_mode:false,token_parameter:'auto',system_role:'system',max_output_tokens:2048,daily_requests:20,timeout_seconds:60},{id:'20000000-0000-4000-8000-000000000002',service_id:sid,name:'合成停用模型',model:'synthetic-disabled',kind:'anthropic',base_url:'https://synthetic.example/v1',key_env:null,enabled:false,text:true,vision:false,reasoning:true,json_mode:false,token_parameter:'auto',system_role:'system',max_output_tokens:2048,daily_requests:20,timeout_seconds:60}],task_defaults:{summary:'20000000-0000-4000-8000-999999999999'},rules:{global_preferences:{style:'清晰、自然地记录生活；合成验收数据。'},content_types:{},templates:{}}}
const calls:any[]=[],stats={generate:0,lists:0,saves:0};Object.defineProperty(window,'__aiPreview',{value:stats})
function json(value:unknown,status=200){return new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json','Cache-Control':'no-store'}})}
window.fetch=async(input,options={})=>{
 const raw=typeof input==='string'?input:input instanceof URL?input.toString():input.url,url=new URL(raw,location.origin),path=url.pathname,method=(options.method||'GET').toUpperCase()
 if(url.origin!==location.origin||!path.startsWith('/api/'))throw Error('AI fixture refuses external or unhandled network access')
 if(path==='/api/auth/csrf')return json({csrf_token:'synthetic-fixture-only'})
 if(path==='/api/admin/exchange/settings'){
  if(method==='PUT'){const {expected_revision,...content}=JSON.parse(String(options.body));if(expected_revision!==config.revision)return json({detail:'合成配置修订冲突'},409);config={...content,revision:config.revision+1};stats.saves++}
  return json(config)
 }
 if(path==='/api/admin/content/types')return json([{id:'synthetic-type',slug:'synthetic',name:'合成生活文章',active:true}])
 if(path==='/api/admin/templates')return json([])
 if(path==='/api/admin/exchange/ai/calls')return json({items:calls})
 if(path==='/api/admin/exchange/ai/presets')return json({items:[{id:'openai',name:'OpenAI',kind:'openai',base_url:'https://api.openai.com/v1',docs:'https://platform.openai.com/docs/api-reference/chat'},{id:'ollama',name:'Ollama',kind:'ollama',base_url:'http://127.0.0.1:11434',docs:'https://docs.ollama.com/api/chat'}]})
 if(path.endsWith('/models')){stats.lists++;return json({items:[{id:'synthetic-returned-model',name:'合成列表模型'}],notice:'仅合成返回列表；能力需自行核对。'})}
 if(path==='/api/admin/exchange/ai/generate'){stats.generate++;const data=JSON.parse(String(options.body));const call={id:'synthetic-call',provider_id:data.provider_id,model:'synthetic-model',action:data.action,state:'succeeded',usage_known:true,input_tokens:11,output_tokens:12,replayed:stats.generate>1};calls.unshift(call);return json(call)}
 return json({detail:'合成预览未实现该操作；不会访问真实服务'},404)
}
const router=createRouter({history:createMemoryHistory(),routes:[{path:'/:pathMatch(.*)*',component:Preview}]})
installAppearance();createApp({render:()=>h(RouterView)}).use(router).mount('#app')
