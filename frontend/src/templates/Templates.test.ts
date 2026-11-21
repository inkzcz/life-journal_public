// @vitest-environment jsdom
import { createApp,nextTick,type App } from 'vue'
import { createRouter,createMemoryHistory } from 'vue-router'
import { beforeEach,afterEach,expect,it,vi } from 'vitest'
import TemplateRenderer from '../blog/TemplateRenderer.vue'
import TemplateAdmin from './TemplateAdmin.vue'
import { formGroups } from './types'
import { newField } from '../admin/types'
const api=vi.hoisted(()=>({request:vi.fn()}));vi.mock('../api',()=>api)
let app:App|undefined,root:HTMLDivElement
const flush=async()=>{await new Promise(r=>setTimeout(r,0));await nextTick()}
const f={...newField(),id:'a',name:'原名称'}
const sample={slug:'custom',name:'自由模板',description:'',active:true,fields:[{key:'a',group:'我的分组',field:f}],modules:[{id:'module',kind:'fields',title:'信息',enabled:true,layout:'card',field_ids:['a']},{id:'body',kind:'body',title:'故事',enabled:true,layout:'grid',field_ids:[]}]}
function button(name:string){const el=Array.from(root.querySelectorAll('button')).find(x=>x.textContent?.trim()===name);if(!el)throw Error(name);return el}
async function mount(component:any,props:any={}){const router=createRouter({history:createMemoryHistory(),routes:[{path:'/:all(.*)*',component:{template:'<div />'}}]});await router.push('/admin/templates');await router.isReady();app=createApp(component,props);app.use(router);app.mount(root);await flush();await flush()}
function input(label:string,value:string){const l=Array.from(root.querySelectorAll('label')).find(l=>l.childNodes[0]?.textContent?.trim()===label);const el=l?.querySelector('input,textarea') as HTMLInputElement;el.value=value;el.dispatchEvent(new Event('input',{bubbles:true}))}
beforeEach(()=>{root=document.createElement('div');document.body.append(root);vi.spyOn(window,'confirm').mockReturnValue(true);api.request.mockReset().mockImplementation(async(path:string,options?:RequestInit)=>{if(path==='/admin/templates/presets')return [{...structuredClone(sample),key:'starter'}];if(path==='/admin/templates'&&!options)return [];if(options)return {...JSON.parse(String(options.body)),id:'tpl',type_id:'t',revision:1,version:1,schema_version:1};throw Error(path)})})
afterEach(()=>{app?.unmount();app=undefined;root.remove();vi.restoreAllMocks()})
it('orders reusable modules and retains values omitted from the layout',async()=>{
 const article={title:'故事',type_name:'自由类型',display_date:'2026-10-18',body:'# 正文<script>unsafe()</script><img src=x onerror=unsafe()>',cover:null,media:[],links:[],places:[],fields:[f,{...f,id:'b',name:'保留字段'}],values:{a:0,b:'旧值'}}
 await mount(TemplateRenderer,{article,config:sample});expect(root.querySelectorAll('[data-module]')[0]?.getAttribute('data-module')).toBe('fields');expect(root.textContent).toContain('0');expect(root.querySelector('.template-retained')?.textContent).toContain('旧值');expect(root.querySelector('script,img')).toBeNull()
})
it('only shows enabled modules and sorts date timeline without dropping exact decimals',async()=>{
 const article={fields:[{...f,kind:'date'},{...f,id:'b',kind:'date',name:'起点'}],values:{a:'2026-10-20',b:'2026-10-18'},media:[],places:[],links:[]}
 await mount(TemplateRenderer,{article,config:{modules:[{id:'hidden',kind:'body',enabled:false,field_ids:[]},{id:'dates',kind:'timeline',enabled:true,field_ids:['a','b']}]}})
 expect(root.querySelectorAll('[data-module]')).toHaveLength(1);expect(root.querySelectorAll('time')[0]?.textContent).toBe('2026-10-18')
})
it('groups existing field IDs in first appearance order',()=>{expect(formGroups([f,{...f,id:'b'},{...f,id:'c'}],{form:[{id:'a',group:'第二组'},{id:'b',group:'第一组'},{id:'c',group:'第二组'}]}).map(g=>[g.name,g.fields.map(f=>f.id)])).toEqual([['第二组',['a','c']],['第一组',['b']]])})
it('edits a starter through reused field forms and sends declarative bindings',async()=>{await mount(TemplateAdmin);button('使用自由模板').click();await flush();input('字段名称','修改后名称');input('表单分组','新的分组');await nextTick();input('预览 修改后名称','虚构预览值');await flush();expect(root.querySelector('.template-live-preview')?.textContent).toContain('修改后名称');root.querySelector('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await flush();const call=api.request.mock.calls.find(([,o])=>o?.method==='POST')!;expect(JSON.parse(call[1].body)).toMatchObject({name:'自由模板',fields:[{key:'a',group:'新的分组',field:{id:'a',name:'修改后名称'}}],modules:[{field_ids:['a']},{kind:'body'}]})})
it('preserves unsaved changes after server conflict and cancels an unsaved template',async()=>{await mount(TemplateAdmin);button('使用自由模板').click();await flush();input('模板名称','尚未保存');await flush();api.request.mockRejectedValueOnce(Error('模板已更新'));root.querySelector('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await flush();expect(root.querySelector('[role=alert]')?.textContent).toContain('模板已更新');expect((root.querySelector('form input') as HTMLInputElement).value).toBe('尚未保存');button('取消模板修改').click();await flush();expect(root.querySelector('form')).toBeNull()})

it('uses the immutable schema order for field cards regardless of checkbox selection order',async()=>{
 const article={fields:[f,{...f,id:'b',name:'第二个'}],values:{a:'甲',b:'乙'},media:[],places:[],links:[]}
 await mount(TemplateRenderer,{article,config:{modules:[{id:'card',kind:'fields',enabled:true,field_ids:['b','a']}]}})
 expect(Array.from(root.querySelectorAll('.template-cards dt')).map(x=>x.textContent)).toEqual(['原名称','第二个'])
})
