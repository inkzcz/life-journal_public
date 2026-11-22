// @vitest-environment jsdom
import { createApp,h,nextTick,type App } from 'vue'
import { createRouter,createMemoryHistory,RouterView,type Router } from 'vue-router'
import { it,expect,vi,beforeEach,afterEach } from 'vitest'
import AdminContent from './AdminContent.vue'
import { emptyConnections } from './archive'
import { emptyLife } from '../life/types'
import { blankSite } from '../blog/types'
const api=vi.hoisted(()=>({request:vi.fn()}));vi.mock('../api',()=>api)
let app:App,root:HTMLDivElement,router:Router,record:any
const flush=async()=>{await new Promise(r=>setTimeout(r,0));await nextTick()}
function button(name:string){const b=Array.from(root.querySelectorAll('button')).find(b=>b.textContent?.trim()===name);if(!b)throw Error(name);return b}
async function body(value:string){await nextTick();const toggle=Array.from(root.querySelectorAll('button')).find(b=>b.textContent?.trim()==='Markdown 源码');if(toggle){toggle.click();await nextTick()}const e=root.querySelector<HTMLTextAreaElement>('.body-editor textarea')!;e.value=value;e.dispatchEvent(new Event('input',{bubbles:true}));await nextTick()}
async function edit(){button('内容记录').click();await flush();button('合成记录任意类型 · 草稿 · 2026-10-19').click();await flush();button('编辑记录').click();await flush();await vi.dynamicImportSettled();await nextTick();expect(root.querySelector('.body-editor')).not.toBeNull()}
beforeEach(async()=>{
 vi.spyOn(window,'confirm').mockReturnValue(false)
 Object.defineProperty(window,'matchMedia',{configurable:true,value:()=>({matches:false,addEventListener(){},removeEventListener(){}})})
 Object.defineProperty(HTMLDialogElement.prototype,'showModal',{configurable:true,value:function(){this.open=true}})
 Object.defineProperty(HTMLDialogElement.prototype,'close',{configurable:true,value:function(){this.open=false;this.dispatchEvent(new Event('close'))}})
 record={id:'r',type_id:'t',type_name:'任意类型',type_active:true,revision:1,schema_version:1,current_type_version:1,title:'合成记录',body:'原正文',display_date:'2026-10-19',status:'draft',fields:[],values:{},connections:emptyConnections(),life:emptyLife()}
 api.request.mockReset().mockImplementation(async(path:string,options?:RequestInit)=>{
  if(path==='/admin/content/types')return [{id:'t',name:'任意类型',active:true}]
  if(path==='/admin/templates')return []
  if(path.startsWith('/admin/content/records?'))return {items:[structuredClone(record)],total:1}
  if(path==='/admin/content/records/r'){
   if(options){const p=JSON.parse(String(options.body));record={...record,...p,connections:{...p.connections,incoming:[]},revision:record.revision+1};return structuredClone(record)}
   return structuredClone(record)
  }
  if(path==='/blog/site')return blankSite()
  if(path.startsWith('/admin/blog/preview/'))return {...record,cover:null,media:[],places:[],links:[],sections:[],template:null,preview_revision:record.revision}
  throw Error(path)
 })
 root=document.createElement('div');document.body.append(root)
 router=createRouter({history:createMemoryHistory(),routes:[{path:'/admin/content',component:AdminContent},{path:'/other',component:{render:()=>h('p','其他页面')}}]})
 app=createApp({render:()=>h(RouterView)}).use(router);await router.push('/admin/content');await router.isReady();app.mount(root);await flush()
})
afterEach(()=>{app.unmount();root.remove();vi.restoreAllMocks();vi.useRealTimers()})
it('blocks route leave and refresh while dirty, and only leaves after explicit discard',async()=>{
 await edit();await body('未保存内容')
 await router.push('/other');expect(router.currentRoute.value.path).toBe('/admin/content');expect(root.querySelector('textarea')?.value).toBe('未保存内容')
 const event=new Event('beforeunload',{cancelable:true});window.dispatchEvent(event);expect(event.defaultPrevented).toBe(true)
 vi.mocked(window.confirm).mockReturnValue(true);await router.push('/other');expect(root.textContent).toContain('其他页面')
 expect(api.request.mock.calls.filter(([,o])=>o?.method==='PUT')).toHaveLength(0)
})
it('autosaves the full draft payload without leaving the editor',async()=>{
 await edit();vi.useFakeTimers();await body('自动保存正文');await vi.advanceTimersByTimeAsync(3000);await nextTick()
 const put=api.request.mock.calls.find(([,o])=>o?.method==='PUT')!
 expect(JSON.parse(String(put[1]?.body))).toMatchObject({status:'draft',body:'自动保存正文',expected_revision:1,connections:{media:[],links:[],places:[]},life:{activities:[],photos:[]}})
 expect(root.querySelector('textarea')?.value).toBe('自动保存正文');expect(root.querySelector('.save-status')?.textContent).toContain('已保存')
})
it('prevents session expiration from discarding unconfirmed edits, and keeps the error visible',async()=>{
 await edit();api.request.mockRejectedValueOnce(Object.assign(new Error('登录过期'),{status:401}));await body('保留在本页');button('保存记录').click();await flush()
 const event=new Event('session-expired',{cancelable:true});window.dispatchEvent(event);expect(event.defaultPrevented).toBe(true)
 expect(root.querySelector('textarea')?.value).toBe('保留在本页');expect(root.textContent).toContain('在新标签页重新登录');expect(root.querySelector('.save-status')?.textContent).toContain('保存失败')
})
it('saves a draft before real preview, pins its revision, and never publishes',async()=>{
 await edit();await body('# 当前未保存预览<script>bad()</script>');button('保存草稿并真实预览').click();await flush();await flush()
 expect(root.querySelector('.editor-preview')?.getAttribute('open')).not.toBeNull()
 expect(root.querySelector('.editor-preview')?.textContent).toContain('未发布预览')
 expect(root.querySelector('.editor-preview .blog-prose')?.textContent).toContain('当前未保存预览')
 expect(root.querySelector('.editor-preview script')).toBeNull();expect(record.status).toBe('draft')
 expect(api.request.mock.calls.some(([p])=>p==='/admin/blog/preview/r?expected_revision=2')).toBe(true)
 button('返回编辑').click();await nextTick();expect(root.querySelector('.editor-preview')).toBeNull();expect(root.querySelector('textarea')?.value).toContain('当前未保存预览')
})
it('does not autosave a published record or use preview as a publication bypass',async()=>{
 record.status='published';button('内容记录').click();await flush();button('合成记录任意类型 · 已发布（私人） · 2026-10-19').click();await flush();button('编辑记录').click();await flush();await vi.dynamicImportSettled();await nextTick();expect(root.querySelector('.body-editor')).not.toBeNull()
 vi.useFakeTimers();await body('不能自动改写发布版');await vi.advanceTimersByTimeAsync(5000)
 expect(api.request.mock.calls.some(([,o])=>o?.method==='PUT')).toBe(false)
 button('真实预览已保存修订').click();await vi.advanceTimersByTimeAsync(0);expect(root.querySelector('.editor-preview')).toBeNull()
 button('保存记录').click();await vi.advanceTimersByTimeAsync(0);expect(window.confirm).toHaveBeenCalled();expect(api.request.mock.calls.some(([,o])=>o?.method==='PUT')).toBe(false)
})

it('retains the confirmed manual-save notice after refreshing the list',async()=>{await edit();await body('手动保存的正文');button('保存记录').click();await flush();await flush();expect(root.querySelector('.admin-content>.notice')?.textContent).toContain('记录已保存');expect(record.body).toBe('手动保存的正文')})

it.each([['draft','published'],['published','draft']] as const)('requires explicit confirmation for %s to %s instead of autosaving the status change',async(initial,target)=>{
 record.status=initial;button('内容记录').click();await flush();button(`合成记录任意类型 · ${initial==='draft'?'草稿':'已发布（私人）'} · 2026-10-19`).click();await flush();button('编辑记录').click();await flush();await vi.dynamicImportSettled();await nextTick();expect(root.querySelector('.body-editor')).not.toBeNull()
 vi.useFakeTimers();const select=root.querySelector<HTMLSelectElement>('select[aria-label="记录状态"]')!;select.value=target;select.dispatchEvent(new Event('change',{bubbles:true}));await nextTick();await vi.advanceTimersByTimeAsync(5000)
 expect(api.request.mock.calls.some(([,o])=>o?.method==='PUT')).toBe(false)
 button(initial==='draft'?'保存草稿并真实预览':'真实预览已保存修订').click();await vi.advanceTimersByTimeAsync(0);expect(root.querySelector('.editor-preview')).toBeNull();expect(record.status).toBe(initial)
 button('保存记录').click();await vi.advanceTimersByTimeAsync(0);expect(record.status).toBe(initial);expect(window.confirm).toHaveBeenCalled()
 vi.mocked(window.confirm).mockReturnValue(true);button('保存记录').click();await vi.advanceTimersByTimeAsync(0);await nextTick();expect(record.status).toBe(target);expect(api.request.mock.calls.filter(([,o])=>o?.method==='PUT')).toHaveLength(1)
})

it('tag-only edits participate in autosave, unload protection and the same revision payload',async()=>{
 record.tags=[{id:'tag-1',name:'京都'}];await edit();vi.useFakeTimers()
 root.querySelector<HTMLButtonElement>('.tag-picker button[aria-label="移除标签京都"]')!.click();await nextTick()
 const event=new Event('beforeunload',{cancelable:true});window.dispatchEvent(event);expect(event.defaultPrevented).toBe(true)
 await vi.advanceTimersByTimeAsync(3000);await nextTick()
 const put=api.request.mock.calls.find(([,o])=>o?.method==='PUT')!
 expect(JSON.parse(String(put[1]?.body))).toMatchObject({tag_ids:[],body:'原正文',status:'draft',expected_revision:1})
})

it('a manual save response cannot unmount or disable an ongoing source composition',async()=>{
 await edit();await body('开始保存的正文')
 const original=api.request.getMockImplementation()!;let finish!:()=>void,releaseList!:()=>void,hold=false
 api.request.mockImplementation((p:string,o?:RequestInit)=>{
  if(o?.method==='PUT')return new Promise(resolve=>{finish=()=>{hold=true;Promise.resolve(original(p,o)).then(resolve)}})
  if(hold&&p.startsWith('/admin/content/records?'))return new Promise(resolve=>{releaseList=()=>Promise.resolve(original(p,o)).then(resolve)})
  return original(p,o)
 })
 button('保存记录').click();await flush();const input=root.querySelector<HTMLTextAreaElement>('.body-editor textarea')!;input.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true}));input.value+='最终汉字';input.dispatchEvent(new Event('input',{bubbles:true}));finish();await flush();await flush()
 expect(root.querySelector('.body-editor textarea')).toBe(input);expect(input.value).toContain('最终汉字');expect(root.querySelector<HTMLFieldSetElement>('.record-compose>fieldset')!.disabled).toBe(false)
 releaseList();input.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true}));await new Promise(r=>setTimeout(r,40));await nextTick();expect(root.querySelector<HTMLTextAreaElement>('.body-editor textarea')!.value).toContain('最终汉字')
})

it('uses Ctrl/Cmd+S only during editing, preserves draft state, and unregisters the shortcut',async()=>{
 const outside=new KeyboardEvent('keydown',{key:'s',ctrlKey:true,cancelable:true});window.dispatchEvent(outside);expect(outside.defaultPrevented).toBe(false)
 await edit();await body('快捷键保存的草稿')
 const save=new KeyboardEvent('keydown',{key:'s',ctrlKey:true,cancelable:true});window.dispatchEvent(save);expect(save.defaultPrevented).toBe(true);await flush();await flush()
 expect(record.body).toBe('快捷键保存的草稿');expect(record.status).toBe('draft')
 button('编辑记录').click();await flush();await vi.dynamicImportSettled();await body('输入法编辑中')
 const prose=root.querySelector('.body-editor textarea')!;prose.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true}))
 const calls=api.request.mock.calls.filter(([,options])=>options?.method==='PUT').length
 window.dispatchEvent(new KeyboardEvent('keydown',{key:'s',metaKey:true,cancelable:true,isComposing:true}));await flush()
 expect(api.request.mock.calls.filter(([,options])=>options?.method==='PUT')).toHaveLength(calls)
})

it('keeps the same body editor and unsaved content when immersive workspace modules switch',async()=>{
 router.addRoute({path:'/write/r',component:AdminContent,props:{immersive:true,recordId:'r'}})
 await router.push('/write/r');await flush();await vi.dynamicImportSettled();await nextTick()
 await body('切换模块仍保留的正文')
 const source=root.querySelector('.body-editor textarea')!,editorNode=root.querySelector('.body-editor')!
 button('基本信息').click();await nextTick();expect(root.querySelector('.body-editor')).toBe(editorNode)
 button('图片与资源').click();await nextTick();button('正文编辑').click();await nextTick()
 expect(root.querySelector('.body-editor textarea')).toBe(source);expect((source as HTMLTextAreaElement).value).toBe('切换模块仍保留的正文')
 expect(root.querySelector('[aria-current=step]')?.textContent).toBe('正文编辑')
 expect(api.request.mock.calls.filter(([,options])=>options?.method==='PUT')).toHaveLength(0)
})

it('saves the explicit travel toggle both ways without changing body, identity or itinerary data',async()=>{
 record.marker_version=2;record.article={end_date:'2026-10-21',travel_enabled:true};record.life={...emptyLife(),start_date:'2026-10-19',end_date:'2026-10-21',activities:[{id:'retained-activity',day:'2026-10-19',time:null,title:'保留活动',description:'原有行程',place_id:null,media_ids:[]}]}
 const old=structuredClone(record)
 await edit()
 for(const enabled of [false,true]){
  const radio=root.querySelector<HTMLInputElement>('.article-mode input[value="'+(enabled?'travel':'daily')+'"]')!;radio.checked=true;radio.dispatchEvent(new Event('change',{bubbles:true}));await flush();button('保存记录').click();await flush();await flush()
  expect(record.article.travel_enabled).toBe(enabled);expect(record.id).toBe(old.id);expect(record.body).toBe(old.body);expect(record.life.activities).toEqual(old.life.activities)
  if(!enabled){button('编辑记录').click();await flush()}
 }
 const puts=api.request.mock.calls.filter(([,o])=>o?.method==='PUT').map(([,o])=>JSON.parse(String(o?.body)));expect(puts.every(p=>p.marker_version===2)).toBe(true)
})
