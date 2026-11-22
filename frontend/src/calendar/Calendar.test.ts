// @vitest-environment jsdom
import {createApp,nextTick,type App} from 'vue'
import {it,expect,vi,afterEach} from 'vitest'
import CalendarPage from './CalendarPage.vue'
const api=vi.hoisted(()=>({request:vi.fn()}))
vi.mock('../api',()=>api)
vi.mock('vue-router',()=>({useRoute:()=>({query:{}})}))
vi.mock('../admin/PrivatePreview.vue',()=>({default:{props:['id'],template:'<img :data-media-id="id"/>'}}))
let app:App,root:HTMLElement
async function flush(){for(let i=0;i<8;i++){await Promise.resolve();await nextTick()}}
function setup(admin=true){api.request.mockImplementation(async(path:string,options?:any)=>{
 if(path==='/admin/status'){if(!admin)throw Error('forbidden');return {is_admin:true}}
 if(path.startsWith('/calendar?'))return {today:'2026-11-13',items:[]}
 if(path==='/admin/calendar/events'&&options?.method==='POST')return {id:'synthetic-event'}
 if(path==='/admin/calendar/events')return []
 if(path==='/admin/calendar/notification')return {enabled:false,url_template:'',timezone:'Asia/Shanghai',time:'09:00',expected_revision:0}
 if(path.startsWith('/admin/calendar/logs'))return []
 if(path==='/calendar/synthetic-event')return {name:'合成生日',upcoming:[],day_memories:[],dedicated_memories:[]}
 return {}
})}
async function mount(){root=document.createElement('div');document.body.append(root);app=createApp(CalendarPage);app.component('RouterLink',{template:'<a><slot/></a>'});app.mount(root);await flush()}
const button=(text:string)=>Array.from(root.querySelectorAll('button')).find(b=>b.textContent===text)!
afterEach(()=>{app?.unmount();root?.remove();vi.clearAllMocks()})
it('renders six complete weeks and changes month through the real API query',async()=>{setup();await mount();expect(root.querySelectorAll('[role=gridcell]')).toHaveLength(42);const first=api.request.mock.calls.find(([p])=>p.startsWith('/calendar?'))![0];button('下个月').click();await flush();const calls=api.request.mock.calls.filter(([p])=>p.startsWith('/calendar?'));expect(calls.at(-1)![0]).not.toBe(first)})
it('keeps notification configuration and mutation controls out of the reader UI',async()=>{setup(false);await mount();expect(root.textContent).not.toContain('GET 通知设置');expect(root.querySelector('input[type=password]')).toBeNull();expect(api.request.mock.calls.some(([p])=>p.startsWith('/admin/calendar'))).toBe(false)})
it('sends independent day-of and advance nodes from the actual calendar form',async()=>{setup();await mount();button('新增纪念日').click();await flush();const form=root.querySelector<HTMLFormElement>('.calendar-form')!;const name=form.querySelector<HTMLInputElement>('input[maxlength="200"]')!;name.value='合成生日';name.dispatchEvent(new Event('input',{bubbles:true}));form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await flush();const call=api.request.mock.calls.find(([p,o])=>p==='/admin/calendar/events'&&o?.method==='POST')!;const d=JSON.parse(call[1].body);expect(d.name).toBe('合成生日');expect(d.reminders).toMatchObject({on_day:true,offsets:[7,3,1],enabled:true});expect(root.querySelector('.calendar-form')).toBeNull()})
it('retains entered event data on a conflict instead of clearing the form',async()=>{setup();await mount();button('新增纪念日').click();await flush();const form=root.querySelector<HTMLFormElement>('.calendar-form')!;const name=form.querySelector<HTMLInputElement>('input[maxlength="200"]')!;name.value='冲突时保留';name.dispatchEvent(new Event('input',{bubbles:true}));const fallback=api.request.getMockImplementation()!;api.request.mockImplementation((p,o)=>p==='/admin/calendar/events'&&o?.method==='POST'?Promise.reject(Error('conflict')):fallback(p,o));form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await flush();expect(root.querySelector<HTMLInputElement>('.calendar-form input[maxlength="200"]')?.value).toBe('冲突时保留');expect(root.textContent).toContain('当前输入保留')})

it('shows the complete editable URL only in admin settings and preserves path templates verbatim on save',async()=>{
 setup();await mount()
 const input=root.querySelector<HTMLInputElement>('input[aria-label="通知 URL 模板"]')!
 expect(input.type).toBe('text')
 expect(root.querySelectorAll('input[aria-label="通知 URL 模板"]')).toHaveLength(1)
 expect(root.querySelector('input[type=password]')).toBeNull()
 const value='https://wxpusher.zjiecode.com/api/send/message/SPT_SYNTHETIC_ONLY/{content}?title={title}'
 input.value=value;input.dispatchEvent(new Event('input',{bubbles:true}));await nextTick()
 expect(input.value).toBe(value)
 button('保存通知设置').click();await flush()
 const call=api.request.mock.calls.find(([p,o])=>p==='/admin/calendar/notification'&&o?.method==='PUT')!
 expect(JSON.parse(call[1].body)).toMatchObject({url_template:value,expected_revision:0})
})

it('does not repeat notification URLs or synthetic provider credentials in failures',async()=>{
 setup();await mount()
 const value='https://notify.example.invalid/send/SYNTHETIC_PRIVATE_VALUE/{content}'
 const input=root.querySelector<HTMLInputElement>('input[aria-label="通知 URL 模板"]')!;input.value=value;input.dispatchEvent(new Event('input',{bubbles:true}));await nextTick()
 api.request.mockRejectedValueOnce(Error('Synthetic backend failure containing '+value))
 button('保存通知设置').click();await flush()
 expect(input.value).toBe(value);expect(root.textContent).toContain('当前输入保留')
 expect(root.textContent).not.toContain(value);expect(root.textContent).not.toContain('SYNTHETIC_PRIVATE_VALUE')
})

it('shows the complete editable URL only to an administrator and keeps failure details out of the page',async()=>{
 setup();await mount()
 const url='https://notify.example.invalid/SPT_SYNTHETIC_ONLY/{content}?title={title}'
 const input=root.querySelector<HTMLInputElement>('input[aria-label="通知 URL 模板"]')!
 expect(input.type).toBe('text')
 expect(root.querySelectorAll('input[aria-label="通知 URL 模板"]')).toHaveLength(1)
 expect(root.querySelector('input[type=password]')).toBeNull();input.value=url;input.dispatchEvent(new Event('input',{bubbles:true}));await nextTick()
 const fallback=api.request.getMockImplementation()!
 api.request.mockImplementation((p,o)=>p==='/admin/calendar/notification'&&o?.method==='PUT'?Promise.reject(Error(url)):fallback(p,o))
 button('保存通知设置').click();await flush()
 expect(input.value).toBe(url);expect(root.textContent).not.toContain(url)
 expect(root.textContent).toContain('当前输入保留')
 const call=api.request.mock.calls.find(([p,o])=>p==='/admin/calendar/notification'&&o?.method==='PUT')!
 expect(JSON.parse(call[1].body).url_template).toBe(url)
})
