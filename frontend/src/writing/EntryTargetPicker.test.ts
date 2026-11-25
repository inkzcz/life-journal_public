// @vitest-environment jsdom
import {createApp,nextTick,type App} from 'vue'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import Picker from './EntryTargetPicker.vue'
import {blankEntry} from './entries'
const mock=vi.hoisted(()=>({request:vi.fn()}))
vi.mock('../api',()=>({request:mock.request}))
let app:App,root:HTMLElement
const flush=async()=>{await Promise.resolve();await Promise.resolve();await nextTick()}
const originalShow=Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype,'showModal'),originalClose=Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype,'close')
beforeEach(()=>{
 mock.request.mockReset()
 Object.defineProperty(HTMLDialogElement.prototype,'showModal',{configurable:true,value:function(this:HTMLDialogElement){this.open=true}})
 Object.defineProperty(HTMLDialogElement.prototype,'close',{configurable:true,value:function(this:HTMLDialogElement){this.open=false}})
 root=document.createElement('div');document.body.append(root)
})
afterEach(()=>{
 app?.unmount();root?.remove();vi.restoreAllMocks()
 if(originalShow)Object.defineProperty(HTMLDialogElement.prototype,'showModal',originalShow);else delete (HTMLDialogElement.prototype as any).showModal
 if(originalClose)Object.defineProperty(HTMLDialogElement.prototype,'close',originalClose);else delete (HTMLDialogElement.prototype as any).close
})
it('requests only a bounded scalar picker, confirms chosen target and cancels explicitly',async()=>{
 const selected=vi.fn(),cancel=vi.fn(),entry=blankEntry();entry.name='合成卡片'
 mock.request.mockResolvedValue({items:[{id:'target',title:'合成目标',revision:7,date:'2026-11-25',travel_enabled:false,status:'draft'}],total:1})
 app=createApp(Picker,{entry,operation:'move',sourceId:'source',onConfirm:selected,onCancel:cancel});app.mount(root);await flush()
 expect(mock.request.mock.calls[0]![0]).toContain('/entry-targets?')
 expect(mock.request.mock.calls[0]![0]).toContain('exclude_id=source')
 const radio=root.querySelector('input[type=radio]') as HTMLInputElement;radio.checked=true;radio.dispatchEvent(new Event('change',{bubbles:true}));await flush()
 const confirm=Array.from(root.querySelectorAll('button')).find(b=>b.textContent==='确认移动')!;confirm.click()
 expect(selected).toHaveBeenCalledWith(expect.objectContaining({id:'target',revision:7}))
 root.querySelector('dialog')!.dispatchEvent(new Event('cancel',{cancelable:true}));expect(cancel).toHaveBeenCalledOnce()
})
