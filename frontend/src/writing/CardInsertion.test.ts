// @vitest-environment jsdom
import {createApp,h,nextTick,ref,type App} from 'vue'
import {afterEach,expect,it,vi} from 'vitest'
import {TextSelection} from '@tiptap/pm/state'
import BodyEditor from './BodyEditor.vue'
import {cardCommandMatch} from './caret'
import {bodyTree} from './body'
import {sourceEntryInsertion} from './sourceEntryInsertion'
import {entryLocations,blankEntry,serializeEntry} from './entries'
vi.mock('../api',()=>({request:vi.fn(async(path:string)=>path.includes('folders')?[]:path.includes('notification')?{timezone:'Asia/Shanghai'}:{items:[]}),uploadImage:vi.fn()}))
let app:App|undefined,root:HTMLElement|undefined
const originalShow=Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype,'showModal'),originalClose=Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype,'close')
const settle=async()=>{await nextTick();await new Promise(r=>setTimeout(r,0));await nextTick()}
afterEach(()=>{app?.unmount();root?.remove();vi.restoreAllMocks();for(const [key,descriptor] of [['showModal',originalShow],['close',originalClose]] as const){if(descriptor)Object.defineProperty(HTMLDialogElement.prototype,key,descriptor);else delete (HTMLDialogElement.prototype as unknown as Record<string,unknown>)[key]}})
function button(parent:ParentNode,text:string){const el=Array.from(parent.querySelectorAll('button')).find(b=>b.textContent?.trim()===text);expect(el,text).toBeTruthy();el!.click()}
async function mount(value:string,mode:'source'|'visual'='source'){
 Object.defineProperty(HTMLDialogElement.prototype,'showModal',{configurable:true,value:function(this:HTMLDialogElement){this.setAttribute('open','')}})
 Object.defineProperty(HTMLDialogElement.prototype,'close',{configurable:true,value:function(this:HTMLDialogElement){this.removeAttribute('open');this.dispatchEvent(new Event('close'))}})
 vi.spyOn(window,'scrollTo').mockImplementation(()=>{});Object.defineProperty(Range.prototype,'getClientRects',{configurable:true,value:()=>[]});Object.defineProperty(Range.prototype,'getBoundingClientRect',{configurable:true,value:()=>({left:0,top:0,right:0,bottom:0,width:0,height:0})})
 const body=ref(value),format=ref(2),component=ref<InstanceType<typeof BodyEditor>>()
 root=document.createElement('div');document.body.append(root);app=createApp({render:()=>h(BodyEditor,{ref:component,modelValue:body.value,format:format.value,recordDate:'2026-01-02','onUpdate:modelValue':(v:string)=>body.value=v,'onUpdate:format':(v:number)=>format.value=v})});app.mount(root);await settle()
 if(mode==='source'&&!root.querySelector('textarea')){button(root,'Markdown 源码');await settle()}
 return {body,component}
}
async function sourceAt(at:number){const el=root!.querySelector<HTMLTextAreaElement>('textarea')!;el.focus();el.setSelectionRange(at,at);el.dispatchEvent(new Event('input',{bubbles:true}));await settle();return el}
async function save(name='合成卡片'){
 const form=root!.querySelector<HTMLFormElement>('dialog form')!,input=form.querySelector<HTMLInputElement>('input[required]')!;input.value=name;input.dispatchEvent(new Event('input',{bubbles:true}));await settle();form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await settle()
}
it.each(['me@m','a@f','https://example.test/@m','@mail','` @m','`` @m','`` 有 ` 内嵌 @m','<span data-x @m','[标签 @m','[标签](https://test/ @m','\\@m','**正文 @m','*正文 @m','@l[名称]','@f 名称'])('keeps non-command text inert: %s',text=>expect(cardCommandMatch(text)).toBeNull())
it.each(['@m','文字 @f','**已结束** @g','* 已有列表 @s','``已结束`` @t'])('offers a complete command outside closed markup: %s',text=>expect(cardCommandMatch(text)).not.toBeNull())
it.each(['l','f','m','s','g','t'])('confirms @%s explicitly, cancels without mutating adjacent source, and replaces only the command on save',async kind=>{
 const raw='前文 @'+kind+' 后文',at=raw.indexOf(' 后文'),{body,component}=await mount(raw),el=await sourceAt(at)
 expect(body.value).toBe(raw);expect(root!.querySelectorAll('[role=option]')).toHaveLength(2)
 el.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));await settle()
 expect(root!.querySelector<HTMLSelectElement>('dialog select[aria-label="记录类型"]')!.value).toBe(kind);expect(component.value!.hasPending()).toBe(true);expect(body.value).toBe(raw);if(kind==='t')expect(Array.from(root!.querySelectorAll<HTMLInputElement>('dialog input[type=date]')).map(el=>el.value)).toEqual(['2026-01-02','2026-01-02'])
 button(root!.querySelector('dialog')!,'取消');await settle();expect(body.value).toBe(raw);expect(el.selectionStart).toBe(at);expect(component.value!.hasPending()).toBe(false)
 await sourceAt(at);el.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));await settle();await save()
 expect(body.value.startsWith('前文 ')).toBe(true);expect(body.value.endsWith(' 后文')).toBe(true);expect(entryLocations(body.value)[0]!.entry.kind).toBe(kind)
 el.dispatchEvent(new KeyboardEvent('keydown',{key:'z',ctrlKey:true,bubbles:true,cancelable:true}));await settle();expect(body.value).toBe(raw)
 el.dispatchEvent(new KeyboardEvent('keydown',{key:'z',ctrlKey:true,shiftKey:true,bubbles:true,cancelable:true}));await settle();expect(entryLocations(body.value)).toHaveLength(1)
})
it('offers six cards first, supports arrows, Escape and explicit compatibility lookup',async()=>{
 const {body}=await mount('前文 @ 后文'),el=await sourceAt(4)
 expect(Array.from(root!.querySelectorAll('[role=option]')).slice(0,6).map(b=>b.textContent?.trim())).toEqual(['@l 插入地点卡片','@f 插入美食卡片','@m 插入电影卡片','@s 插入演出卡片','@g 插入礼物卡片','@t 插入交通卡片'])
 el.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowDown',bubbles:true,cancelable:true}));await settle();expect(root!.querySelector('[aria-selected=true]')?.textContent).toContain('@f')
 el.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}));await settle();expect(root!.querySelector('.place-suggestions')).toBeNull();expect(body.value).toBe('前文 @ 后文')
 await sourceAt(3);await sourceAt(4);button(root!,'旧版文本标记 ›');await settle();expect(root!.textContent).toContain('旧版文本标记 · 地点搜索与绑定');button(root!,'@s 景点 · 旧版地点绑定');await settle();expect(body.value).toBe('前文 @s  后文');expect(root!.querySelector('dialog[open]')).toBeNull()
})
it('does not confirm shortcuts during IME and blocks mid-token, fenced-code and Markdown-link contexts',async()=>{
 await mount('前文 @m 后文');const el=await sourceAt(5);el.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true}));el.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',isComposing:true,bubbles:true,cancelable:true}));await settle();expect(root!.querySelector('dialog[open]')).toBeNull();el.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true}));await new Promise(r=>setTimeout(r,35));await settle();expect(root!.querySelector('dialog[open]')).toBeNull()
 for(const [raw,at] of [['@movies',2],['```text\n@m\n```',10],['[正文 @m](https://example.test)',6]] as const){el.value=raw;await sourceAt(at);expect(root!.querySelector('.place-suggestions')).toBeNull()}
})
it('toolbar insertion preserves a source selection and article date, and rejects stale dialog positions after an external update',async()=>{
 const {body}=await mount('开头 选中文字 结尾');const el=await sourceAt(3);el.setSelectionRange(3,7);button(root!,'插入卡片');await settle();button(root!.querySelector('dialog')!,'取消');await settle();expect(el.selectionStart).toBe(3);expect(el.selectionEnd).toBe(7)
 button(root!,'插入卡片');await settle();await save();expect(body.value.endsWith('选中文字 结尾')).toBe(true)
 await sourceAt(0);button(root!,'插入卡片');await settle();body.value+='外部修改';await settle();await save();expect(root!.querySelector('dialog[open]')).not.toBeNull();expect(root!.textContent).toContain('正文已变化');expect(entryLocations(body.value)).toHaveLength(1)
})
it('visual shortcut cancel preserves the exact Markdown and bookmark; confirm and undo preserve adjacent text',async()=>{
 const raw='前文 @m 后文',{body}=await mount(raw,'visual');const prose=root!.querySelector('.tiptap') as HTMLElement & {editor:any},e=prose.editor
 e.view.dispatch(e.state.tr.setSelection(TextSelection.create(e.state.doc,6)));prose.focus();prose.dispatchEvent(new KeyboardEvent('keyup',{key:'m',bubbles:true}));await settle()
 // Selection update is measured asynchronously by the real editor.
 e.commands.setTextSelection(5);e.commands.setTextSelection(6);await settle()
 expect(root!.querySelector('[role=option]')?.textContent).toContain('@m')
 button(root!,'@m 插入电影卡片');await settle();expect(body.value).toBe(raw);button(root!.querySelector('dialog')!,'取消');await settle();expect(body.value).toBe(raw);expect(e.state.selection.from).toBe(6)
 e.commands.setTextSelection(5);e.commands.setTextSelection(6);await settle();button(root!,'@m 插入电影卡片');await settle();await save();expect(entryLocations(body.value)).toHaveLength(1);expect(body.value).toContain('前文');expect(body.value).toContain('后文');expect(body.value).not.toContain('@m')
 e.commands.undo();await settle();expect(body.value).toBe(raw);e.commands.redo();await settle();expect(entryLocations(body.value)).toHaveLength(1)
})
it('blocks another visual card mutation and global saving while a local card draft is pending',async()=>{
 const a=blankEntry('m'),b=blankEntry('g');a.name='合成A';b.name='合成B';const {body,component}=await mount(serializeEntry(a)+'\n\n'+serializeEntry(b),'visual'),original=body.value
 const cards=root!.querySelectorAll('.entry-card');button(cards[0]!,'···');await settle();button(document.body,'编辑卡片');await settle();const input=cards[0]!.querySelector<HTMLInputElement>('input[required]')!;input.value='尚未保存';input.dispatchEvent(new Event('input',{bubbles:true}));await settle();expect(component.value!.hasPending()).toBe(true)
 const prose=root!.querySelector('.tiptap')!;for(const key of ['Delete','Backspace','z']){const event=new KeyboardEvent('keydown',{key,ctrlKey:key==='z',bubbles:true,cancelable:true});prose.dispatchEvent(event);expect(event.defaultPrevented).toBe(true)}const drag=new Event('dragstart',{bubbles:true,cancelable:true});prose.dispatchEvent(drag);expect(drag.defaultPrevented).toBe(true);expect(body.value).toBe(original)
 button(cards[1]!,'···');await settle();button(document.body,'复制卡片');await settle();expect(body.value).toBe(original);expect(cards[1]!.textContent).toContain('合成B');button(cards[0]!,'取消');await settle();expect(component.value!.hasPending()).toBe(false)
})

it('preserves list containers and rejects insertion into literal and private metadata',()=>{
 const entry=blankEntry('m');entry.name='合成电影'
 for(const raw of ['- @m','- 前文 @m 后文','1. @m']){const at=raw.indexOf('@m')+2,change=sourceEntryInsertion(raw,at,2,entry);const ids:string[]=[];const walk=(nodes:ReturnType<typeof bodyTree>)=>nodes.forEach(n=>{if(n.entry)ids.push(n.entry.id);if(n.children)walk(n.children)});walk(bodyTree(change.value,2));expect(ids).toEqual([entry.id]);expect(change.value).toContain(raw.startsWith('1')?'1. :::':'- ')}
 for(const raw of ['```text\n@m\n```','<div>\n@m\n</div>','| 标题 |\n|---|\n| @m |'])expect(()=>sourceEntryInsertion(raw,raw.indexOf('@m')+2,2,entry)).toThrow()
 const block=serializeEntry(entry);expect(()=>sourceEntryInsertion(block,block.indexOf('合成电影'),0,entry)).toThrow()
})
