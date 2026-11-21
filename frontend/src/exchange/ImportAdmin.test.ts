// @vitest-environment jsdom
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {createApp,nextTick,type App} from 'vue'
import ImportAdmin from './ImportAdmin.vue'
const api=vi.hoisted(()=>({request:vi.fn()}))
vi.mock('../api',()=>api)
vi.mock('../ui/confirm',()=>({confirmAction:vi.fn(async()=>true)}))
let root:HTMLDivElement,app:App
const flush=async()=>{await new Promise(r=>setTimeout(r,0));await nextTick()}
const button=(name:string)=>Array.from(root.querySelectorAll('button')).find(b=>b.textContent?.trim()===name)!
function preview(){return {id:'11111111-1111-4111-8111-111111111111',revision:1,state:'preview',valid:true,stale_context:false,issues:[],records:[{key:'one',compiled_body:'正式正文',values:{}}],contexts:{one:{type:{fields:[]}}},images:[],result_ids:[],input:{format:'life-journal.exchange',version:1,media:[],places:[],records:[{key:'one',type_slug:'article',title:'导入标题',display_date:'2026-11-05',summary:'',body:'原始正文',values:{},tags:[],media_keys:[],cover_key:null,foods:[],photos:[],links:[],travel:null}]}}}
async function upload(){const input=root.querySelector<HTMLInputElement>('input[type=file]')!;Object.defineProperty(input,'files',{value:[new File(['synthetic'],'sample.json',{type:'application/json'})],configurable:true});input.dispatchEvent(new Event('change',{bubbles:true}));await nextTick();button('生成导入预览').click();await flush()}
beforeEach(async()=>{sessionStorage.clear();root=document.createElement('div');document.body.append(root);api.request.mockReset().mockImplementation(async(path:string)=>path==='/admin/content/types'?[{id:'type',slug:'article',name:'自定义类型',active:true}]:preview());app=createApp(ImportAdmin);app.component('RouterLink',{props:['to'],template:'<a :href="to"><slot/></a>'});app.mount(root);await flush()})
afterEach(()=>{app.unmount();root.remove();sessionStorage.clear();vi.restoreAllMocks();vi.unstubAllGlobals()})
it('requires explicit review and invalidates confirmation whenever mappings change',async()=>{await upload();const confirm=button('确认创建草稿');expect(confirm.disabled).toBe(true);const check=root.querySelector<HTMLInputElement>('input[type=checkbox]')!;check.checked=true;check.dispatchEvent(new Event('change',{bubbles:true}));await nextTick();expect(confirm.disabled).toBe(false);const title=root.querySelector<HTMLInputElement>('.exchange-fields input')!;title.value='新标题';title.dispatchEvent(new Event('input',{bubbles:true}));await nextTick();expect(confirm.disabled).toBe(true);expect(root.textContent).toContain('映射有未校验的修改');expect(api.request.mock.calls.some(([,o])=>o?.method==='POST'&&String(o.body).includes('创建草稿'))).toBe(false)})
it('rechecks mappings with the original revision and keeps typed content on conflict',async()=>{await upload();const title=root.querySelector<HTMLInputElement>('.exchange-fields input')!;title.value='保留新标题';title.dispatchEvent(new Event('input',{bubbles:true}));await nextTick();api.request.mockRejectedValueOnce(Object.assign(Error('预览已更新'),{status:409}));root.querySelector('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await flush();expect(root.querySelector('[role=alert]')?.textContent).toContain('预览已更新');expect(title.value).toBe('保留新标题');const call=api.request.mock.calls.find(([p])=>p.endsWith('/mapping'))!;expect(JSON.parse(call[1].body)).toMatchObject({expected_revision:1,content:{records:[{title:'保留新标题'}]}})})
it('uses a stable upload request key after a response failure without creating content directly',async()=>{api.request.mockRejectedValueOnce(Error('网络中断'));await upload();expect(root.querySelector('[role=alert]')?.textContent).toContain('网络中断');button('生成导入预览').click();await flush();const calls=api.request.mock.calls.filter(([p])=>p==='/admin/exchange/preview');expect(calls).toHaveLength(2);expect(calls[0][1].headers['X-Import-Key']).toBe(calls[1][1].headers['X-Import-Key']);expect(api.request.mock.calls.every(([p])=>!p.startsWith('/admin/content/records'))).toBe(true)})
it('shows draft links only after confirmed creation and sends the confirmation gate',async()=>{await upload();const check=root.querySelector<HTMLInputElement>('input[type=checkbox]')!;check.checked=true;check.dispatchEvent(new Event('change',{bubbles:true}));await nextTick();api.request.mockResolvedValueOnce({...preview(),state:'completed',result_ids:['new-record']});button('确认创建草稿').click();await flush();const call=api.request.mock.calls.find(([p])=>p.endsWith('/confirm'))!;expect(JSON.parse(call[1].body)).toEqual({expected_revision:1,confirmation:'创建草稿'});expect(root.querySelector('a[href="/write/new-record"]')).not.toBeNull();expect(root.textContent).toContain('已创建草稿')})
it('does not confirm a previous preview after choosing a new file, even after reloading it',async()=>{await upload();const check=root.querySelector<HTMLInputElement>('input[type=checkbox]')!;check.checked=true;check.dispatchEvent(new Event('change',{bubbles:true}));await nextTick();expect(button('确认创建草稿').disabled).toBe(false);const input=root.querySelector<HTMLInputElement>('input[type=file]')!;Object.defineProperty(input,'files',{value:[new File(['different'],'second.json')],configurable:true});input.dispatchEvent(new Event('change',{bubbles:true}));await nextTick();expect(button('确认创建草稿').disabled).toBe(true);button('重新读取任务').click();await flush();const again=root.querySelector<HTMLInputElement>('input[type=checkbox]')!;again.checked=true;again.dispatchEvent(new Event('change',{bubbles:true}));await nextTick();expect(button('确认创建草稿').disabled).toBe(true);expect(root.textContent).toContain('新文件尚未上传校验');button('预览新文件 / 重试上传').click();await flush();const uploaded=root.querySelector<HTMLInputElement>('input[type=checkbox]')!;uploaded.checked=true;uploaded.dispatchEvent(new Event('change',{bubbles:true}));await nextTick();expect(button('确认创建草稿').disabled).toBe(false)})
it('renders a valid media key named constructor without inheriting dictionary methods',async()=>{const errors:unknown[]=[];app.config.errorHandler=e=>errors.push(e);const value=preview();value.input.media=[{key:'constructor',existing_id:'33333333-3333-4333-8333-333333333333',path:null,caption:'已有照片',alt:'',width:960,widthPercent:null,align:'center',layout:'auto'}] as any;value.input.records[0].media_keys=['constructor'] as any;api.request.mockResolvedValue(value);await upload();expect(errors).toEqual([]);expect(root.textContent).toContain('采用图片来源')})
it('keeps an unmatched record key named constructor editable instead of treating a prototype as its schema',async()=>{const errors:unknown[]=[];app.config.errorHandler=e=>errors.push(e);const value=preview();value.valid=false;value.contexts={} as any;value.records=[];value.input.records[0].key='constructor';api.request.mockResolvedValue(value);await upload();expect(errors).toEqual([]);expect(root.textContent).toContain('原始正文');expect(button('确认创建草稿').disabled).toBe(true)})

it('keeps an explicitly cleared local default date empty before revalidation instead of resurrecting the previous preview value',async()=>{
 const value=preview(),fid='11111111-2222-4333-8444-555555555555'
 value.contexts.one.type.fields=[{id:fid,name:'本地预设日期',kind:'date',active:true,required:false,has_default:true,rules:{},position:0,description:''}] as any
 value.records[0].values={[fid]:'2026-10-03'};api.request.mockResolvedValue(value);await upload()
 const input=Array.from(root.querySelectorAll('label')).find(label=>label.textContent?.trim()==='本地预设日期')!.querySelector<HTMLInputElement>('input')!
 expect(input.value).toBe('2026-10-03');input.value='';input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));await nextTick()
 expect(input.value).toBe('');expect(button('确认创建草稿').disabled).toBe(true)
})

it('does not show the previous default when previewing an explicitly cleared Markdown field',async()=>{
 const value=preview(),fid='11111111-2222-4333-8444-555555555555'
 value.contexts.one.type.fields=[{id:fid,name:'本地预设文字',kind:'markdown',active:true,required:false,has_default:true,rules:{},position:0,description:''}] as any
 value.records[0].values={[fid]:'不应复活的预设文字'};api.request.mockResolvedValue(value);await upload()
 const area=Array.from(root.querySelectorAll('label')).find(label=>label.textContent?.trim()==='本地预设文字')!.querySelector<HTMLTextAreaElement>('textarea')!
 area.value='';area.dispatchEvent(new Event('input',{bubbles:true}));await nextTick();button('预览字段 Markdown').click();await nextTick()
 expect(root.querySelector('.dynamic-input .markdown')?.textContent).not.toContain('不应复活的预设文字')
})
it('creates a stable secure import key on HTTP without randomUUID',async()=>{
 vi.stubGlobal('crypto',{getRandomValues:crypto.getRandomValues.bind(crypto)})
 await upload();const call=api.request.mock.calls.find(([p])=>p==='/admin/exchange/preview')!
 expect(call[1].headers['X-Import-Key']).toMatch(/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/)
 expect(root.querySelector('[role=alert]')).toBeNull()
})
it('shows an error and blocks the previous preview after a new file cannot obtain a secure identity',async()=>{
 await upload();const check=root.querySelector<HTMLInputElement>('input[type=checkbox]')!;check.checked=true;check.dispatchEvent(new Event('change',{bubbles:true}));await nextTick();expect(button('确认创建草稿').disabled).toBe(false)
 vi.stubGlobal('crypto',{});const input=root.querySelector<HTMLInputElement>('input[type=file]')!;Object.defineProperty(input,'files',{value:[new File(['new'],'new.json')],configurable:true});input.dispatchEvent(new Event('change',{bubbles:true}));await nextTick()
 expect(root.querySelector('[role=alert]')?.textContent).toContain('浏览器不支持安全随机数');expect(button('确认创建草稿').disabled).toBe(true);expect(button('预览新文件 / 重试上传').disabled).toBe(true)
})
