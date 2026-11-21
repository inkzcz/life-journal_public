// @vitest-environment jsdom
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {createApp,nextTick,type App} from 'vue'
import AIAdmin from './AIAdmin.vue'
const api=vi.hoisted(()=>({request:vi.fn()}))
vi.mock('../api',()=>api)
vi.mock('../ui/confirm',()=>({confirmAction:vi.fn(async()=>true)}))
let root:HTMLDivElement,app:App
const flush=async()=>{await new Promise(r=>setTimeout(r,0));await nextTick()}
const button=(name:string)=>Array.from(root.querySelectorAll('button')).find(b=>b.textContent?.trim()===name)!
const initial=()=>({revision:4,providers:[],rules:{global_preferences:{style:'原有文风'},content_types:{},templates:{}}})
beforeEach(async()=>{root=document.createElement('div');document.body.append(root);api.request.mockReset().mockImplementation(async(path:string)=>path.endsWith('/settings')?initial():path.endsWith('/calls')?{items:[]}:[]);app=createApp(AIAdmin);app.mount(root);await flush()})
afterEach(()=>{app.unmount();root.remove();vi.restoreAllMocks();vi.unstubAllGlobals()})
it('cancels unsaved rules locally without writing or changing saved defaults',async()=>{const input=root.querySelector<HTMLTextAreaElement>('textarea')!;input.value='未保存文风';input.dispatchEvent(new Event('input',{bubbles:true}));await nextTick();expect(root.textContent).toContain('有未保存修改');button('取消修改').click();await flush();expect(root.querySelector<HTMLTextAreaElement>('textarea')!.value).toBe('原有文风');expect(api.request.mock.calls.every(([,o])=>!o?.method)).toBe(true)})
it('retains user configuration on 409 and sends expected revision',async()=>{const input=root.querySelector<HTMLTextAreaElement>('textarea')!;input.value='保留这个输入';input.dispatchEvent(new Event('input',{bubbles:true}));await nextTick();api.request.mockRejectedValueOnce(Object.assign(Error('配置已被修改'),{status:409}));button('保存配置').click();await flush();expect(root.querySelector('[role=alert]')?.textContent).toContain('配置已被修改');expect(input.value).toBe('保留这个输入');const call=api.request.mock.calls.find(([,o])=>o?.method==='PUT')!;expect(JSON.parse(call[1].body)).toMatchObject({expected_revision:4,rules:{global_preferences:{style:'保留这个输入'}}})})
it('uses dedicated environment references and creates disabled providers without accepting raw API keys',async()=>{button('添加模型配置').click();await flush();const provider=root.querySelector('.ai-provider')!;expect(provider.textContent).toContain('密钥环境变量引用');expect(provider.querySelector<HTMLInputElement>('input[type=checkbox]')!.checked).toBe(false);expect(provider.querySelector('input[type=password]')).toBeNull();expect(root.textContent).toContain('不会自动发送照片')})
it('treats constructor as an owned custom type scope without mutating the global Object',async()=>{app.unmount();root.innerHTML='';api.request.mockImplementation(async(path:string)=>path.endsWith('/settings')?initial():path.endsWith('/calls')?{items:[]}:path==='/admin/content/types'?[{id:'type',slug:'constructor',name:'合法自定义类型',active:true}]:[]);app=createApp(AIAdmin);app.mount(root);await flush();const select=Array.from(root.querySelectorAll<HTMLSelectElement>('select')).find(s=>Array.from(s.options).some(o=>o.value==='type'))!;select.value='type';select.dispatchEvent(new Event('change',{bubbles:true}));await nextTick();const target=Array.from(root.querySelectorAll('label')).find(l=>l.textContent?.startsWith('稳定配置对象'))!.querySelector<HTMLSelectElement>('select')!;target.value='constructor';target.dispatchEvent(new Event('change',{bubbles:true}));await nextTick();expect(button('为此对象自定义规则')).toBeTruthy();button('为此对象自定义规则').click();await nextTick();const style=root.querySelector<HTMLTextAreaElement>('textarea')!;style.value='构造类型独立规则';style.dispatchEvent(new Event('input',{bubbles:true}));await nextTick();button('保存配置').click();await flush();const call=api.request.mock.calls.find(([,opts])=>opts?.method==='PUT')!;expect(JSON.parse(call[1].body).rules.content_types.constructor).toEqual({style:'构造类型独立规则'});expect(Object.prototype.hasOwnProperty.call(Object,'style')).toBe(false)})

it('adds, saves and reloads a provider when NAS HTTP has getRandomValues but no randomUUID',async()=>{
 const getRandomValues=crypto.getRandomValues.bind(crypto);vi.stubGlobal('crypto',{getRandomValues})
 let stored=initial() as any
 api.request.mockImplementation(async(path:string,options?:any)=>{if(path.endsWith('/settings')){if(options?.method==='PUT'){const {expected_revision,...content}=JSON.parse(options.body);expect(expected_revision).toBe(4);stored={...content,revision:5}}return JSON.parse(JSON.stringify(stored))}return path.endsWith('/calls')?{items:[]}:[]})
 button('添加模型配置').click();await flush();expect(root.querySelectorAll('.ai-provider')).toHaveLength(1)
 const model=Array.from(root.querySelectorAll('label')).find(l=>l.textContent?.startsWith('Model ID'))!.querySelector('input')!;model.value='synthetic-model';model.dispatchEvent(new Event('input',{bubbles:true}));await nextTick()
 button('保存配置').click();await flush();expect(root.querySelector('[role=alert]')).toBeNull();expect(root.textContent).toContain('配置已保存')
 const id=stored.providers[0].id;expect(id).toMatch(/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/)
 app.unmount();root.innerHTML='';app=createApp(AIAdmin);app.mount(root);await flush();expect(root.querySelectorAll('.ai-provider')).toHaveLength(1);expect(root.textContent).toContain('已保存配置');expect(stored.providers[0].id).toBe(id)
 expect(Array.from(root.querySelectorAll('input')).some(i=>i.value==='synthetic-model')).toBe(true)
})
it('explains secure randomness failure without partially adding or saving a provider',async()=>{
 vi.stubGlobal('crypto',{});button('添加模型配置').click();await flush()
 expect(root.querySelector('[role=alert]')?.textContent).toContain('浏览器不支持安全随机数');expect(root.querySelectorAll('.ai-provider')).toHaveLength(0)
 expect(button('保存配置').disabled).toBe(true);expect(api.request.mock.calls.some(([,o])=>o?.method)).toBe(false)
})
it('uses fallback request UUIDs and reuses the same connection-test key without repeating a new paid identity',async()=>{
 vi.stubGlobal('crypto',{getRandomValues:crypto.getRandomValues.bind(crypto)})
 app.unmount();root.innerHTML='';const provider={id:'11111111-1111-4111-8111-111111111111',name:'合成模型',kind:'ollama',model:'synthetic-model',enabled:true}
 api.request.mockImplementation(async(path:string)=>path.endsWith('/settings')?{...initial(),providers:[provider]}:path.endsWith('/calls')?{items:[]}:path==='/admin/content/types'?[{id:'type',slug:'synthetic',name:'合成类型',active:true}]:path.endsWith('/generate')?{state:'succeeded',replayed:true}:[])
 app=createApp(AIAdmin);app.mount(root);await flush();const type=Array.from(root.querySelectorAll('label')).find(l=>l.textContent?.startsWith('连接测试使用的内容类型'))!.querySelector('select')!;type.value='synthetic';type.dispatchEvent(new Event('change',{bubbles:true}));await nextTick()
 button('测试 / 核对连接').click();await flush();button('测试 / 核对连接').click();await flush()
 const calls=api.request.mock.calls.filter(([p])=>p.endsWith('/generate'));expect(calls).toHaveLength(2);const key=JSON.parse(calls[0][1].body).request_key;expect(key).toMatch(/^[a-f0-9-]{14}4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/);expect(JSON.parse(calls[1][1].body).request_key).toBe(key)
})
