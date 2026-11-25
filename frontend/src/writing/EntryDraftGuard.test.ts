// @vitest-environment jsdom
import {createApp,h,nextTick,ref,type App} from 'vue'
import {afterEach,expect,it,vi} from 'vitest'
import BodyEditor from './BodyEditor.vue'
import {blankEntry,serializeEntry,entryLocations} from './entries'
vi.mock('../api',()=>({request:vi.fn().mockResolvedValue([]),uploadImage:vi.fn()}))
let app:App|undefined,root:HTMLElement|undefined
const originalShow=Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype,'showModal'),originalClose=Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype,'close')
const settle=async()=>{await nextTick();await new Promise(r=>setTimeout(r,0));await nextTick()}
afterEach(()=>{app?.unmount();root?.remove();vi.restoreAllMocks();for(const [key,descriptor] of [['showModal',originalShow],['close',originalClose]] as const){if(descriptor)Object.defineProperty(HTMLDialogElement.prototype,key,descriptor);else delete (HTMLDialogElement.prototype as unknown as Record<string,unknown>)[key]}})
async function mount(){
 const a=blankEntry('m'),b=blankEntry('m');a.name='合成已保存 A';b.name='合成已保存 B'
 const body=ref('合成正文\n\n'+serializeEntry(a)+'\n\n'+serializeEntry(b)),states:boolean[]=[],editor=ref<InstanceType<typeof BodyEditor>>()
 root=document.createElement('div');document.body.append(root)
 app=createApp({render:()=>h(BodyEditor,{ref:editor,modelValue:body.value,format:2,'onUpdate:modelValue':(v:string)=>body.value=v,onPending:(v:boolean)=>states.push(v)})})
 app.mount(root);await settle()
 return {body,states,editor,ids:[a.id,b.id]}
}
function button(parent:ParentNode,text:string){const el=Array.from(parent.querySelectorAll('button')).find(b=>b.textContent?.trim()===text);expect(el, text).toBeTruthy();el!.click()}
async function edit(index:number,name:string){
 const card=root!.querySelectorAll('.entry-card')[index]!
 button(card,'···');await settle();button(document.body,'编辑卡片');await settle()
 const field=card.querySelector<HTMLInputElement>('form input[required][maxlength="200"]')!
 field.value=name;field.dispatchEvent(new Event('input',{bubbles:true}));await settle();return card
}
it('reports local NodeView drafts before document changes and blocks lossy mode changes until cancel',async()=>{
 const {body,states}=await mount(),original=body.value,card=await edit(0,'合成未保存 A')
 expect(states.at(-1)).toBe(true);expect(body.value).toBe(original)
 button(root!,'Markdown 源码');await settle()
 expect(root!.querySelector('.immersive-prose')).not.toBeNull()
 expect(card.querySelector<HTMLInputElement>('form input[required]')?.value).toBe('合成未保存 A')
 expect(root!.textContent).toContain('请先保存或取消卡片编辑，再切换模式')
 button(card,'取消');await settle();expect(states.at(-1)).toBe(false);expect(body.value).toBe(original)
 button(root!,'Markdown 源码');await settle();expect(root!.querySelector('textarea')?.value).toBe(original)
})
it('keeps every other card draft pending when one is cancelled, then allows saving without changing UUIDs',async()=>{
 const {body,states,ids}=await mount(),first=await edit(0,'合成取消 A'),second=await edit(1,'合成保存 B')
 button(first,'取消');await settle();expect(states.at(-1)).toBe(true)
 button(second,'保存卡片');await settle();expect(states.at(-1)).toBe(false)
 const cards=entryLocations(body.value).map(c=>c.entry)
 expect(cards.map(c=>c.id)).toEqual(ids);expect(cards.map(c=>c.name)).toEqual(['合成已保存 A','合成保存 B'])
})
it('rejects AI capture and previously captured replacement while a card draft is outside the document',async()=>{
 const {body,editor}=await mount(),original=body.value,capture=editor.value!.captureAI()!
 expect(capture).not.toBeNull();const card=await edit(0,'合成未保存 A')
 expect(editor.value!.captureAI()).toBeNull()
 expect(editor.value!.applyAI(capture.id,'合成替换','replace')).toBe(false)
 expect(body.value).toBe(original);expect(card.querySelector<HTMLInputElement>('form input[required]')?.value).toBe('合成未保存 A')
})
it('reports new-card modal drafts and clears their pending state on native close',async()=>{
 Object.defineProperty(HTMLDialogElement.prototype,'showModal',{configurable:true,value:function(this:HTMLDialogElement){this.setAttribute('open','')}})
 Object.defineProperty(HTMLDialogElement.prototype,'close',{configurable:true,value:function(this:HTMLDialogElement){this.removeAttribute('open');this.dispatchEvent(new Event('close'))}})
 const {states}=await mount();button(root!,'@ 结构化记录');await settle();expect(states.at(-1)).toBe(true)
 button(root!.querySelector('dialog.entry-dialog')!,'取消');await settle();expect(states.at(-1)).toBe(false)
})
