// @vitest-environment jsdom
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {createApp,h,ref,nextTick,type App} from 'vue'
import WritingAssistant from './WritingAssistant.vue'
import type {AIApply} from './selection'
const api=vi.hoisted(()=>({request:vi.fn()}))
vi.mock('../api',()=>api)
vi.mock('../ui/confirm',()=>({confirmAction:vi.fn(async()=>true)}))
vi.mock('vue-router',()=>({useRouter:()=>({push:vi.fn()})}))
let app:App,root:HTMLDivElement
let apply=vi.fn((_id:string,_text:string,_mode:AIApply):boolean=>false)
const flush=async()=>{await new Promise(r=>setTimeout(r,0));await nextTick()}
const button=(name:string)=>Array.from(root.querySelectorAll('button')).find(b=>b.textContent?.trim()===name)!
function result(){return {id:'call',state:'succeeded',job_id:'job',preview:{valid:true,stale_context:false,issues:[],input:{media:[],places:[],records:[{title:'候选标题',body:'安全候选',summary:'',tags:[],foods:[],links:[],values:{},travel:null}]}}}}
async function prepare(){button('固定选区与发送范围').click();await nextTick();const check=Array.from(root.querySelectorAll('label')).find(l=>l.textContent?.includes('我确认将标题'))!.querySelector<HTMLInputElement>('input')!;check.checked=true;check.dispatchEvent(new Event('change',{bubbles:true}));await nextTick()}
beforeEach(async()=>{root=document.createElement('div');document.body.append(root);apply=vi.fn((_id:string,_text:string,_mode:AIApply):boolean=>false);api.request.mockReset().mockImplementation(async(path:string)=>path.endsWith('/settings')?{revision:2,providers:[{id:'provider',name:'模拟',enabled:true,model:'mock'}]}:path.includes('/requests/')?{id:'call'}:result());app=createApp(WritingAssistant,{typeSlug:'article',title:'原题',displayDate:'2026-11-05',capture:()=>({id:'anchor',body:'完整正文含未选择的内容',selection:'仅选中的文字',mode:'source',format:2}),apply});app.mount(root);await flush()})
afterEach(()=>{app.unmount();root.remove();vi.restoreAllMocks()})
it('sends only explicitly captured selection after consent and never applies automatically',async()=>{expect(button('生成并预览').disabled).toBe(true);await prepare();button('生成并预览').click();await flush();const call=api.request.mock.calls.find(([p])=>p.endsWith('/generate'))!;expect(JSON.parse(call[1].body)).toMatchObject({body:'仅选中的文字',consent:true,type_slug:'article'});expect(String(call[1].body)).not.toContain('完整正文含未选择的内容');expect(root.querySelector('.assistant-result')?.textContent).toContain('安全候选');expect(apply).not.toHaveBeenCalled()})
it('reuses the original request identity after a lost response instead of paying twice',async()=>{await prepare();api.request.mockImplementation(async(path:string)=>{if(path.endsWith('/generate'))throw Error('网络中断');return {id:'call'}});button('生成并预览').click();await flush();expect(root.querySelector('[role=alert]')?.textContent).toContain('同一请求核对');button('生成并预览').click();await flush();const calls=api.request.mock.calls.filter(([p])=>p.endsWith('/generate'));expect(calls).toHaveLength(2);expect(JSON.parse(calls[0][1].body).request_key).toBe(JSON.parse(calls[1][1].body).request_key)})
it('delegates selection checks to the editor and reports refusal without changing content',async()=>{await prepare();button('生成并预览').click();await flush();button('替换原选区').click();await flush();expect(apply).toHaveBeenCalledWith('anchor','安全候选','selection');expect(root.textContent).toContain('候选未应用')})
it('does not enable direct body replacement for structured resource proposals',async()=>{await prepare();api.request.mockImplementation(async(path:string)=>{if(path.includes('/requests/'))return {id:'call'};const value=result();value.preview.input.places=[{key:'place'}] as any;return value});button('生成并预览').click();await flush();expect(button('替换全部正文').disabled).toBe(true);expect(button('在原光标插入').disabled).toBe(true);expect(apply).not.toHaveBeenCalled()})
it('permits preserved resources only when their identities were in the captured scope',async()=>{app.unmount();root.innerHTML='';const id='11111111-1111-4111-8111-111111111111',body=':::lj-media-v1\n'+JSON.stringify({id})+'\n:::';app=createApp(WritingAssistant,{typeSlug:'article',title:'原题',displayDate:'2026-11-05',capture:()=>({id:'anchor',body,selection:body,mode:'source',format:2}),apply});app.mount(root);await flush();await prepare();api.request.mockImplementation(async(path:string)=>{if(path.includes('/requests/'))return {id:'call'};const value=result();value.preview.input.records[0].body=body;value.preview.input.media=[{key:'kept-media-0',existing_id:id}] as any;return value});button('生成并预览').click();await flush();expect(button('替换原选区').disabled).toBe(false);button('替换原选区').click();await flush();expect(apply).toHaveBeenCalledWith('anchor',body,'selection')})

 it('refuses a late candidate after the content type changes without replaying a paid request',async()=>{
  app.unmount();root.innerHTML='';const type=ref('original');let finish:(value:any)=>void=()=>{}
  api.request.mockImplementation((path:string)=>path.endsWith('/settings')?Promise.resolve({revision:2,providers:[{id:'provider',name:'模拟',enabled:true,model:'mock'}]}):path.includes('/requests/')?Promise.resolve({id:'call'}):new Promise(resolve=>finish=resolve))
  app=createApp({render:()=>h(WritingAssistant,{typeSlug:type.value,title:'原题',displayDate:'',capture:()=>({id:'anchor',body:'原正文',selection:'原正文',mode:'source' as const,format:2}),apply:(id,text,mode)=>Boolean(apply(id,text,mode))})});app.mount(root);await flush();await prepare();button('生成并预览').click();await flush();type.value='new-type';await nextTick();finish(result());await flush()
  expect(root.querySelector('.assistant-result')).toBeNull();expect(root.textContent).toContain('文章结构或元信息已变化');expect(apply).not.toHaveBeenCalled();expect(api.request.mock.calls.filter(([p])=>p.endsWith('/generate'))).toHaveLength(1)
 })
 it('routes a complete creation candidate to the shared mapping preview and has no direct body apply actions',async()=>{
  app.unmount();root.innerHTML='';const preview=vi.fn();app=createApp(WritingAssistant,{creation:true,typeSlug:'custom',title:'',displayDate:'',capture:()=>({id:'new',body:'',selection:'',mode:'source',format:2}),apply,onPreview:preview});app.mount(root);await flush();await prepare();button('生成并预览').click();await flush()
  expect(root.textContent).not.toContain('替换全部正文');button('转到导入预览创建新草稿').click();await flush();expect(preview).toHaveBeenCalledWith('job');expect(apply).not.toHaveBeenCalled();expect(api.request.mock.calls.some(([p])=>p.startsWith('/admin/content/records'))).toBe(false)
 })
