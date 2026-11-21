// @vitest-environment jsdom
import { createApp, nextTick, type App } from 'vue'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import AdminContent from './AdminContent.vue'
import { fieldPayload, initialValues, newField } from './types'
const api=vi.hoisted(()=>({request:vi.fn()}));vi.mock('../api',()=>api)
const field={...newField(),id:'field-1',name:'自定义名字',required:true,has_default:true,default_value:'默认内容'}
const type={id:'type-1',slug:'custom',name:'任意类型',description:'说明',active:true,revision:1,version:1,fields:[field]}
let app:App,root:HTMLDivElement
const flush=async()=>{await new Promise(r=>setTimeout(r,0));await nextTick()}
function button(text:string){const b=Array.from(root.querySelectorAll('button')).find(b=>b.textContent?.trim()===text);if(!b)throw Error(text);return b}
function labelled(text:string){const label=Array.from(root.querySelectorAll('label')).find(l=>l.childNodes[0]?.textContent?.trim()===text);if(!label)throw Error(text);return label.querySelector('input,textarea,select') as HTMLInputElement}
async function input(text:string,value:string){const e=labelled(text);e.value=value;e.dispatchEvent(new Event('input',{bubbles:true}));await nextTick()}
async function submit(){root.querySelector('form')!.dispatchEvent(new Event('submit',{cancelable:true,bubbles:true}));await flush()}
beforeEach(async()=>{api.request.mockReset().mockImplementation(async(path:string,options?:RequestInit)=>{
 if(path==='/admin/templates')return []
 if(path==='/admin/content/types'&&!options)return [type]
 if(path==='/admin/content/types/type-1'&&!options)return structuredClone(type)
 if(path.startsWith('/admin/content/records?'))return {items:[],total:0}
 if(options)return {...type,...JSON.parse(String(options.body))}
 throw Error(path)
});vi.spyOn(window,'confirm').mockReturnValue(true);root=document.createElement('div');document.body.append(root);app=createApp(AdminContent);app.mount(root);await flush()})
afterEach(()=>{app.unmount();root.remove();vi.restoreAllMocks()})
it('creates a freely named content type with normal form fields',async()=>{button('创建类型').click();await flush();await input('类型名称','自由记录');await input('稳定标识','free-notes');button('添加字段').click();await nextTick();await input('字段名称','自选属性');await submit();const call=api.request.mock.calls.find(([,o])=>o?.method==='POST')!;expect(JSON.parse(call[1].body)).toMatchObject({name:'自由记录',slug:'free-notes',fields:[{name:'自选属性',position:0,kind:'short_text'}]})})
it('preserves saved field identity and sends expected revision',async()=>{button('任意类型启用中 · custom').click();await flush();await input('字段名称','字段改名');await submit();const call=api.request.mock.calls.find(([,o])=>o?.method==='PUT')!;expect(JSON.parse(call[1].body)).toMatchObject({expected_revision:1,fields:[{id:'field-1',name:'字段改名'}]});expect(root.textContent).not.toContain('移除未保存字段')})
it('generates record inputs, applies defaults and retains edits on conflict',async()=>{button('内容记录').click();await flush();button('新建记录').click();await flush();expect(labelled('自定义名字 *').value).toBe('默认内容');await input('记录标题','草稿保留');await input('自定义名字 *','新值');api.request.mockRejectedValueOnce(Error('记录已被其他页面修改'));await submit();expect(root.querySelector('[role=alert]')?.textContent).toContain('其他页面');expect(labelled('记录标题').value).toBe('草稿保留');expect(labelled('自定义名字 *').value).toBe('新值')})
it('uses safe Markdown in the generated editor',async()=>{button('内容记录').click();await flush();button('新建记录').click();await flush();await vi.dynamicImportSettled();await nextTick();expect(root.querySelector('.body-editor')).not.toBeNull();button('Markdown 源码').click();await nextTick();await input('记录正文（Markdown）','# 正文<script>bad()</script><img src="https://example.com/private">');button('预览正文 Markdown').click();await nextTick();expect(root.querySelector('.article-body h1')?.textContent).toContain('正文');expect(root.querySelector('.article-body script')).toBeNull();expect(root.querySelector('.article-body img')).toBeNull()})
it('does not replace existing historical values with new defaults',()=>{expect(initialValues([field],{'field-1':'历史值'})).toEqual({'field-1':'历史值'});const f=newField();f.rules={min_length:'' as unknown as number};f.default_value='stale';expect(fieldPayload([f])[0]).toMatchObject({rules:{},default_value:null})})

it('keeps inactive food values visible in advanced settings and never recreates a disabled role',async()=>{
 app.unmount();root.innerHTML=''
 const inactive={...field,purpose:'food_shop',name:'历史店铺字段',required:false,active:false}
 const historical={id:'historical',type_id:type.id,type_name:type.name,type_active:true,is_food:true,schema_version:1,current_type_version:1,title:'合成旧文章',body:'原文保留',body_format:1,display_date:'2026-11-05',status:'published',revision:1,values:{'field-1':'历史旧店铺'},fields:[inactive],connections:{media:[],places:[],links:[],incoming:[]}}
 api.request.mockImplementation(async(path:string)=>path==='/admin/templates'?[]:path==='/admin/content/types'?[type]:path.startsWith('/admin/content/records?')?{items:[],total:0}:path==='/admin/content/records/historical'?historical:[])
 app=createApp(AdminContent,{immersive:true,recordId:'historical'});app.mount(root);await flush();await vi.dynamicImportSettled();await flush()
 expect(root.textContent).toContain('历史店铺字段（已停用，原值保留）：历史旧店铺')
 expect(root.textContent).toContain('餐厅字段已在模板中停用')
 expect(root.textContent).not.toContain('启用餐厅信息字段（请先保存当前修改）')
 expect(api.request.mock.calls.some(([,options])=>options?.method==='POST')).toBe(false)
})
