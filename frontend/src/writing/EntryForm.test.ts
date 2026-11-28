// @vitest-environment jsdom
import {createApp,h,nextTick,reactive,type App} from 'vue'
import {afterEach,expect,it,vi} from 'vitest'
import EntryForm from './EntryForm.vue'
import {blankEntry,transportType} from './entries'
vi.mock('../api',()=>({request:vi.fn(async()=>({timezone:'Asia/Shanghai'}))}))
let app:App,root:HTMLElement
function mount(fields:Record<string,string>={}){const entry=reactive(blankEntry('t'));entry.name='合成车次';entry.fields=fields;root=document.createElement('div');document.body.append(root);app=createApp({render:()=>h(EntryForm,{value:entry,recordDate:'2026-12-31'})});app.mount(root);return entry}
afterEach(()=>{app?.unmount();root?.remove()})
async function select(value:string){const input=root.querySelector('[aria-label="交通类型"]') as HTMLSelectElement;input.value=value;input.dispatchEvent(new Event('change',{bubbles:true}));await nextTick()}
it('maps historical free text without modifying it on mount and keeps unknown fields editable',async()=>{
 const fields={transport_type:'历史特别列车',terminal:'合成历史航站楼',custom_memory:'第一行\n第二行',place_id:'11111111-1111-4111-8111-111111111111'},before=JSON.stringify(fields),entry=mount(fields)
 await nextTick();expect(JSON.stringify(entry.fields)).toBe(before)
 expect(root.textContent).toContain('历史兼容信息');expect(Array.from(root.querySelectorAll('textarea')).some(t=>t.value===fields.custom_memory)).toBe(true)
 expect(entry.fields.place_id).toBe(fields.place_id)
})
it('switches six transport variants without clearing prior input or identity and exposes photos and notes',async()=>{
 const entry=mount({transport_type:'高铁',carriage:'05',seat:'08A',airline:'合成航空',review:'保留感受'}),id=entry.id
 expect(root.querySelectorAll('[aria-label="交通类型"] option')).toHaveLength(6)
 await select('飞机');expect(root.textContent).toContain('航空公司');expect(root.querySelector('details')?.textContent).not.toContain('车厢')
 await select('高铁／动车');expect(root.textContent).toContain('车厢');expect(entry.fields.carriage).toBe('05');expect(entry.fields.airline).toBe('合成航空');expect(entry.id).toBe(id)
 expect(entry.fields.legacy_transport_type).toBe('高铁');expect(root.querySelector('details:last-child')?.hasAttribute('open')).toBe(true)
 expect(Array.from(root.querySelectorAll('textarea')).some(t=>t.value==='保留感受')).toBe(true)
})
it.each([['动车','高铁／动车'],['train','普通列车'],['航班 flight','飞机'],['驾车','自驾'],['ferry','轮船'],['合成缆车','其他']])('maps %s non-destructively to %s',(raw,result)=>expect(transportType(raw)).toBe(result))
