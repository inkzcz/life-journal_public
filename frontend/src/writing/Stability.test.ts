// @vitest-environment jsdom
import {it,expect,vi,afterEach} from 'vitest'
import {createApp,h,nextTick,ref,type App} from 'vue'
import * as api from '../api'
import BodyEditor from './BodyEditor.vue'
import PlaceSuggest from './PlaceSuggest.vue'
import {suggestionMatch,popupPosition} from './caret'
vi.mock('../api',()=>({request:vi.fn(async(path:string)=>path.includes('folders')?[]:{items:[]}),uploadImage:vi.fn()}))
let app:App|undefined,root:HTMLDivElement|undefined
const wait=()=>new Promise(r=>setTimeout(r,40))
afterEach(()=>{app?.unmount();root?.remove();vi.restoreAllMocks()})
it.each(['@','第一行\n@','普通段落 @','- @','  - @','## @','今天，@','午餐：@f '])('matches supported context %s',s=>expect(suggestionMatch(s)).not.toBeNull())
it.each(['me@example','https://x/@','正文@','`@f ','@f 名称 {#place:uuid} '])('does not suggest unrelated text %s',s=>expect(suggestionMatch(s)).toBeNull())
it('clamps and flips popup in the viewport',()=>{const p=popupPosition({left:innerWidth,top:innerHeight-20,bottom:innerHeight},200,180);expect(p.left+200).toBeLessThanOrEqual(innerWidth);expect(p.top+180).toBeLessThan(innerHeight)})
it('retains source composition DOM against stale external values and publishes the final character',async()=>{
 const value=ref('|表格|\n|---|\n|正文|'),update=vi.fn((v:string)=>value.value=v)
 root=document.createElement('div');document.body.append(root);app=createApp({render:()=>h(BodyEditor,{modelValue:value.value,'onUpdate:modelValue':update})});app.mount(root);await nextTick();await nextTick()
 const input=root.querySelector('textarea')!;input.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true}));input.value+='最终汉字';input.dispatchEvent(new Event('input',{bubbles:true}));value.value='过期的外部响应';await nextTick();expect(input.value).toContain('最终汉字');expect(update).not.toHaveBeenCalled()
 input.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true}));await wait();await nextTick();expect(update).toHaveBeenLastCalledWith(expect.stringContaining('最终汉字'));expect(input.value).toContain('最终汉字')
})
it('Esc invalidates an outstanding suggestion search',async()=>{
 root=document.createElement('div');document.body.append(root);app=createApp(PlaceSuggest,{context:'@f 餐厅',composing:false});const vm=app.mount(root) as unknown as {key:(e:KeyboardEvent)=>void};await nextTick();vm.key(new KeyboardEvent('keydown',{key:'Escape'}));await new Promise(r=>setTimeout(r,210));expect(root.querySelector('[role=option]')).toBeNull();expect(root.textContent).not.toContain('可继续输入')
})

it('does not rewrite the textarea value on native input, preserving selection and native undo',async()=>{
 const value=ref('|列|\n|---|\n|内容|')
 root=document.createElement('div');document.body.append(root);app=createApp({render:()=>h(BodyEditor,{modelValue:value.value,'onUpdate:modelValue':(s:string)=>value.value=s})});app.mount(root);await nextTick();await nextTick()
 const input=root.querySelector('textarea')!;input.value+='新字';input.setSelectionRange(3,3);const setter=vi.spyOn(input,'value','set');input.dispatchEvent(new Event('input',{bubbles:true}));await nextTick();expect(setter).not.toHaveBeenCalled();expect(input.selectionStart).toBe(3);expect(value.value).toContain('新字')
})

it('keeps the final composed character when an in-flight image completes during IME',async()=>{
 let complete!:(v:unknown)=>void;vi.mocked(api.uploadImage).mockReturnValueOnce(new Promise(r=>complete=r))
 const value=ref('|列|\n|---|\n|内容|')
 root=document.createElement('div');document.body.append(root);app=createApp({render:()=>h(BodyEditor,{modelValue:value.value,'onUpdate:modelValue':(s:string)=>value.value=s})});app.mount(root);await nextTick();await nextTick()
 const input=root.querySelector('textarea')!;input.focus();input.setSelectionRange(input.value.length,input.value.length)
 const file=root.querySelector<HTMLInputElement>('input[type=file]')!;Object.defineProperty(file,'files',{value:[new File(['synthetic'],'synthetic.jpg',{type:'image/jpeg'})]});file.dispatchEvent(new Event('change',{bubbles:true}));await nextTick()
 input.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true}));input.value+='最终汉字';input.dispatchEvent(new Event('input',{bubbles:true}));complete({id:'11111111-1111-4111-8111-111111111111',filename:'synthetic.jpg'});await new Promise(r=>setTimeout(r,10));expect(input.value).toContain('最终汉字');expect(document.activeElement).toBe(input)
 input.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true}));await wait();await nextTick();expect(value.value).toContain('最终汉字');expect(value.value).toContain(':::lj-media-v1');expect(input.value).toContain('最终汉字')
})

it('an asynchronous upload never steals focus from another field',async()=>{
 let complete!:(v:unknown)=>void;vi.mocked(api.uploadImage).mockReturnValueOnce(new Promise(r=>complete=r))
 const value=ref('|列|\n|---|\n|内容|');root=document.createElement('div');document.body.append(root);app=createApp({render:()=>h('div',[h('input',{id:'other'}),h(BodyEditor,{modelValue:value.value,'onUpdate:modelValue':(s:string)=>value.value=s})])});app.mount(root);await nextTick();await nextTick()
 const source=root.querySelector('textarea')!;source.focus();const file=root.querySelector<HTMLInputElement>('input[type=file]')!;Object.defineProperty(file,'files',{value:[new File(['synthetic'],'synthetic.jpg',{type:'image/jpeg'})]});file.dispatchEvent(new Event('change',{bubbles:true}));await nextTick();const other=root.querySelector<HTMLInputElement>('#other')!;other.focus();complete({id:'11111111-1111-4111-8111-111111111111',filename:'synthetic.jpg'});await wait();expect(document.activeElement).toBe(other);expect(value.value).toContain(':::lj-media-v1')
})

it('closes source suggestions on blur and does not reopen them on viewport updates',async()=>{
 const value=ref('|列|\n|---|\n|内容|\n\n@')
 root=document.createElement('div');document.body.append(root);app=createApp({render:()=>h('div',[h('input',{id:'other'}),h(BodyEditor,{modelValue:value.value,'onUpdate:modelValue':(s:string)=>value.value=s})])});app.mount(root);await nextTick();await nextTick()
 const input=root.querySelector('textarea')!;input.focus();input.setSelectionRange(input.value.length,input.value.length);input.dispatchEvent(new Event('input',{bubbles:true}));await wait();expect(root.querySelector('.place-suggestions')).not.toBeNull()
 root.querySelector<HTMLInputElement>('#other')!.focus();window.dispatchEvent(new Event('resize'));await wait();expect(root.querySelector('.place-suggestions')).toBeNull();expect(document.activeElement).toBe(root.querySelector('#other'))
})

it('ignores a late place lookup after the caret changes to a different context',async()=>{
 const {request}=await import('../api');let finish!:(v:unknown)=>void
 vi.mocked(request).mockImplementationOnce(()=>new Promise(r=>finish=r))
 const context=ref('@f 旧餐厅');root=document.createElement('div');document.body.append(root);app=createApp({render:()=>h(PlaceSuggest,{context:context.value,composing:false})});app.mount(root)
 await new Promise(r=>setTimeout(r,200));context.value='无补全上下文';await nextTick();finish({items:[{active:true,id:'old-place',name:'不应插入的旧结果'}]});await wait();expect(root.querySelector('[role=option]')).toBeNull();expect(root.textContent).not.toContain('不应插入')
})

it('maps an in-flight visual image bookmark through intervening edits',async()=>{
 const {TextSelection}=await import('@tiptap/pm/state');let complete!:(v:unknown)=>void;vi.mocked(api.uploadImage).mockReturnValueOnce(new Promise(r=>complete=r))
 const value=ref('开头文字 结尾文字');root=document.createElement('div');document.body.append(root);app=createApp({render:()=>h(BodyEditor,{modelValue:value.value,format:2,'onUpdate:modelValue':(s:string)=>value.value=s})});app.mount(root);await nextTick();await wait()
 const prose=root.querySelector('.tiptap') as HTMLElement & {editor:{view:any}};const view=prose.editor.view
 view.dispatch(view.state.tr.setSelection(TextSelection.create(view.state.doc,6)));prose.focus()
 const file=root.querySelector<HTMLInputElement>('input[type=file]')!;Object.defineProperty(file,'files',{value:[new File(['synthetic'],'mapped.jpg',{type:'image/jpeg'})]});file.dispatchEvent(new Event('change',{bubbles:true}));await nextTick()
 view.dispatch(view.state.tr.insertText('前置',1));complete({id:'11111111-1111-4111-8111-111111111111',filename:'mapped.jpg'});await wait()
 expect(value.value).toContain('前置开头文字');expect(value.value.indexOf('mapped.jpg')).toBeGreaterThan(value.value.indexOf('前置开头文字'));expect(value.value.indexOf('mapped.jpg')).toBeLessThan(value.value.indexOf('结尾文字'))
})
