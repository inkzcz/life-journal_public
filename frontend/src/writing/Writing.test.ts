// @vitest-environment jsdom
import {createApp,h,nextTick,type App} from 'vue'
import {it,expect,vi,afterEach} from 'vitest'
import {Editor} from '@tiptap/core'
import {TextSelection,NodeSelection} from '@tiptap/pm/state'
import {indentVisualText} from './visualKeys'
import {writingExtensions} from './extensions'
import {bodyParts,bodyMedia,serializeMedia,visualCompatible} from './body'
import BodyEditor from './BodyEditor.vue'
import ArticleBody from '../reading/ArticleBody.vue'
const api=vi.hoisted(()=>({request:vi.fn(),uploadImage:vi.fn()}));vi.mock('../api',()=>api)
const media={id:'11111111-1111-4111-8111-111111111111',alt:'合成山景',caption:'私人记忆',width:720,align:'center' as const}
let editor:Editor|undefined,app:App|undefined,root:HTMLElement|undefined
afterEach(()=>{editor?.destroy();editor=undefined;app?.unmount();app=undefined;root?.remove();vi.restoreAllMocks()})
it('round trips supported Chinese Markdown and versioned media without storing HTML',()=>{
 const original='## 合成中文章节\n\n这是 **粗体** 和 *斜体*。\n\n'+serializeMedia(media)+'\n\n- 第一项\n- 第二项\n\n> 引用\n'
 editor=new Editor({extensions:writingExtensions(),content:original,contentType:'markdown'})
 const result=editor.getMarkdown();expect(result).toContain('**粗体**');expect(result).toContain('*斜体*');expect(result).toContain('## 合成中文章节');expect(bodyParts(result,2).filter(p=>p.media).map(p=>p.media)).toEqual([media]);expect(result).not.toContain('<img')
})
it('keeps fenced/indented samples inert and does not interpret old body format',()=>{
 const block=serializeMedia(media)
 expect(bodyParts('```text\n'+block+'\n```',2).some(p=>p.media)).toBe(false)
 expect(bodyParts(block.split('\n').map(l=>'    '+l).join('\n'),2).some(p=>p.media)).toBe(false)
 expect(bodyParts(block,1).some(p=>p.media)).toBe(false)
 expect(bodyParts('> '+block.replaceAll('\n','\n> '),2).some(p=>p.media)).toBe(false)
})
it('falls back to source for tables, active HTML and remote images',()=>{
 for(const value of ['|列|\n|---|\n|值|','<script>alert(1)</script>','![tracking](https://example.com/pixel)',':::lj-media-v2\n{}\n:::'])expect(visualCompatible(value)).toBe(false)
 expect(visualCompatible('普通中文\n\n- 列表')).toBe(true)
})
it('renders authenticated media only and keeps heading numbers stable across images',async()=>{
 api.request.mockResolvedValue(new Blob());vi.stubGlobal('IntersectionObserver',undefined);URL.createObjectURL=vi.fn(()=> 'blob:synthetic');URL.revokeObjectURL=vi.fn()
 root=document.createElement('div');document.body.append(root);app=createApp({render:()=>h(ArticleBody,{source:'## 开始\n\n'+serializeMedia(media)+'\n\n## 结束',namespace:'test',format:2})});app.mount(root);await new Promise(r=>setTimeout(r,0));await nextTick();await nextTick()
 expect(Array.from(root.querySelectorAll('[data-reading-heading]')).map(e=>e.id)).toEqual(['lj-test-heading-1','lj-test-heading-2'])
 expect(root.textContent).toContain('私人记忆');expect(api.request.mock.calls.some(([path])=>path==='/library-media/'+media.id+'/preview')).toBe(true);expect(root.querySelector('img')?.src).toBe('blob:synthetic')
})

it('does not rewrite an untouched old Markdown body on mount or mode switches',async()=>{
 const original='## 中文标题\n\n保留  两个空格与 **文字**。\n'
 const update=vi.fn();root=document.createElement('div');document.body.append(root);app=createApp({render:()=>h(BodyEditor,{modelValue:original,format:1,'onUpdate:modelValue':update})});app.mount(root);await nextTick();await nextTick()
 function toggle(name:string){const b=Array.from(root!.querySelectorAll('button')).find(b=>b.textContent?.trim()===name)!;b.click()}
 toggle('Markdown 源码');await nextTick();expect(root.querySelector('textarea')?.value).toBe(original)
 toggle('可视化编辑');await nextTick();toggle('Markdown 源码');await nextTick();expect(update).not.toHaveBeenCalled();expect(root.querySelector('textarea')?.value).toBe(original)
})
it('keeps unsupported old Markdown in source without destructive conversion',async()=>{
 const original='| 字段 | 内容 |\n|---|---|\n| 原文 | 保留 |'
 const update=vi.fn();root=document.createElement('div');document.body.append(root);app=createApp({render:()=>h(BodyEditor,{modelValue:original,format:1,'onUpdate:modelValue':update})});app.mount(root);await nextTick()
 expect(root.querySelector('textarea')?.value).toBe(original);expect(root.querySelector('.immersive-prose')).toBeNull();expect(update).not.toHaveBeenCalled()
})
it('blocks saving during Chinese IME composition in visual and source modes',async()=>{
 const pending=vi.fn();root=document.createElement('div');document.body.append(root);app=createApp(BodyEditor,{modelValue:'合成中文',format:1,onPending:pending});app.mount(root);await nextTick();await nextTick()
 const prose=root.querySelector('.immersive-prose')!;prose.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true,data:'拼'}));expect(pending).toHaveBeenLastCalledWith(true)
 prose.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true,data:'拼音'}));await new Promise(r=>setTimeout(r,40));expect(pending).toHaveBeenLastCalledWith(false)
 Array.from(root.querySelectorAll('button')).find(b=>b.textContent==='Markdown 源码')!.click();await nextTick();const source=root.querySelector('textarea')!
 source.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true}));expect(pending).toHaveBeenLastCalledWith(true);source.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true}));await new Promise(r=>setTimeout(r,40));expect(pending).toHaveBeenLastCalledWith(false)
})

it('adopts new uploads for a historical article without folder, but respects explicit unfiled selection',async()=>{
 api.request.mockResolvedValue([]);api.uploadImage.mockResolvedValue({id:media.id,filename:'synthetic.jpg',alt:''})
 const uploaded=vi.fn();root=document.createElement('div');document.body.append(root);app=createApp(BodyEditor,{modelValue:'原有正文',recordId:'old-record',format:2,onUploaded:uploaded});app.mount(root);await nextTick();await new Promise(r=>setTimeout(r,0))
 Array.from(root.querySelectorAll('button')).find(b=>b.textContent==='Markdown 源码')!.click();await nextTick()
 const file=root.querySelector<HTMLInputElement>('input[type=file]')!;Object.defineProperty(file,'files',{configurable:true,value:[new File(['synthetic'],'synthetic.jpg',{type:'image/jpeg'})]});file.dispatchEvent(new Event('change',{bubbles:true}));await new Promise(r=>setTimeout(r,0));await nextTick();expect(uploaded).toHaveBeenCalledWith(media.id)
 uploaded.mockClear();const folder=root.querySelector<HTMLSelectElement>('select[aria-label="上传到文件夹"]')!;folder.value='';folder.dispatchEvent(new Event('change',{bubbles:true}));await nextTick()
 Object.defineProperty(file,'files',{configurable:true,value:[new File(['synthetic2'],'other.jpg',{type:'image/jpeg'})]});file.dispatchEvent(new Event('change',{bubbles:true}));await new Promise(r=>setTimeout(r,0));await nextTick();expect(api.uploadImage).toHaveBeenCalledTimes(2);expect((api.uploadImage.mock.calls[1]![1] as FormData).get('auto_archive')).toBe('false');expect(uploaded).not.toHaveBeenCalled()
})

it('publishes media format before an uploaded body is observable by synchronous save consumers',async()=>{
 api.request.mockResolvedValue([]);api.uploadImage.mockResolvedValue({id:media.id,filename:'synthetic.jpg',alt:''})
 let format=1;const snapshots:{body:string;format:number}[]=[]
 root=document.createElement('div');document.body.append(root)
 app=createApp(BodyEditor,{modelValue:'原有正文',format:1,'onUpdate:format':(value:number)=>{format=value},'onUpdate:modelValue':(body:string)=>snapshots.push({body,format})})
 app.mount(root);await nextTick();await new Promise(r=>setTimeout(r,0))
 Array.from(root.querySelectorAll('button')).find(b=>b.textContent==='Markdown 源码')!.click();await nextTick()
 const file=root.querySelector<HTMLInputElement>('input[type=file]')!
 Object.defineProperty(file,'files',{value:[new File(['synthetic'],'synthetic.jpg',{type:'image/jpeg'})]})
 file.dispatchEvent(new Event('change',{bubbles:true}));await new Promise(r=>setTimeout(r,0));await nextTick()
 const saved=snapshots.find(s=>s.body.includes(':::lj-media-v1'))
 expect(saved).toBeDefined();expect(saved!.format).toBe(2)
 expect(bodyParts(saved!.body,saved!.format).filter(p=>p.media)).toHaveLength(1)
})

it('keeps nested list media as authenticated nodes through reading and visual roundtrip',async()=>{
 const source='- 10月3日\n  - 下午途经山谷\n\n'+serializeMedia(media).split('\n').map(line=>'    '+line).join('\n')+'\n\n    返回酒店\n'
 expect(visualCompatible(source)).toBe(true)
 editor=new Editor({extensions:writingExtensions(),content:source,contentType:'markdown'})
 expect(editor.getJSON().content?.[0]?.type).toBe('bulletList')
 const serialized=editor.getMarkdown();expect(serialized).toContain(media.id)
 api.request.mockResolvedValue(new Blob());vi.stubGlobal('IntersectionObserver',undefined);URL.createObjectURL=vi.fn(()=> 'blob:nested');URL.revokeObjectURL=vi.fn()
 root=document.createElement('div');document.body.append(root)
 app=createApp({render:()=>h(ArticleBody,{source:serialized,namespace:'nested',format:2})});app.mount(root)
 await new Promise(r=>setTimeout(r,0));await nextTick();await nextTick()
 expect(root.querySelector('ul ul li figure')).not.toBeNull()
 expect(root.textContent).toContain('返回酒店');expect(root.textContent).not.toContain(':::lj-media-v1')
 expect(root.querySelector('img')?.src).toBe('blob:nested')
})

it('keeps visual Tab within text, allows Escape then Tab to reach image controls, and respects IME',async()=>{
 root=document.createElement('div');document.body.append(root)
 app=createApp(BodyEditor,{modelValue:'普通段落',format:1});app.mount(root);await nextTick();await nextTick()
 const prose=root.querySelector('.immersive-prose')!
 const tab=new KeyboardEvent('keydown',{key:'Tab',bubbles:true,cancelable:true});prose.dispatchEvent(tab);expect(tab.defaultPrevented).toBe(true)
 prose.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))
 const exit=new KeyboardEvent('keydown',{key:'Tab',bubbles:true,cancelable:true});prose.dispatchEvent(exit);expect(exit.defaultPrevented).toBe(false)
 prose.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true}))
 const ime=new KeyboardEvent('keydown',{key:'Tab',isComposing:true,bubbles:true,cancelable:true});prose.dispatchEvent(ime);expect(ime.defaultPrevented).toBe(false)
})

it('visual indentation preserves selected text and media atoms instead of replacing the selection',()=>{
 editor=new Editor({extensions:writingExtensions(),content:'第一段\n\n'+serializeMedia(media)+'\n\n第二段',contentType:'markdown'})
 editor.view.dispatch(editor.state.tr.setSelection(TextSelection.create(editor.state.doc,1,editor.state.doc.content.size-1)))
 indentVisualText(editor.view)
 expect(editor.getText()).toContain('第一段');expect(editor.getText()).toContain('第二段');expect(editor.getMarkdown()).toContain(media.id)
 let at=0;editor.state.doc.descendants((node,pos)=>{if(node.type.name==='privateMedia')at=pos})
 editor.view.dispatch(editor.state.tr.setSelection(NodeSelection.create(editor.state.doc,at)))
 const before=editor.getJSON();indentVisualText(editor.view);expect(editor.getJSON()).toEqual(before)
})

it('preserves document-wide reference links across list and private-media fragments',async()=>{
 api.request.mockResolvedValue(new Blob());vi.stubGlobal('IntersectionObserver',undefined);URL.createObjectURL=vi.fn(()=> 'blob:reference');URL.revokeObjectURL=vi.fn()
 const source='[旧链接][story]\n\n- 第一项\n\n'+serializeMedia(media)+'\n\n[另一处链接][story]\n\n@l[合成地区]\n\n[story]: /stories "原链接"\n'
 root=document.createElement('div');document.body.append(root);app=createApp({render:()=>h(ArticleBody,{source,namespace:'references',format:2})});app.mount(root);await nextTick()
 expect(root.querySelectorAll('a[href="/stories"]')).toHaveLength(2)
 expect(root.textContent).not.toContain('[旧链接]');expect(root.querySelector('.lj-place-mark')?.textContent).toContain('合成地区')
})

 it.each([1,2,3])('v516 serializes private media at list depth %i',depth=>{
  const parents=Array.from({length:depth},(_,i)=>'  '.repeat(i)+'- '+(i===depth-1?'@f 合成餐厅':'上层')).join('\n')
  const source=parents+'\n\n'+serializeMedia({...media,widthPercent:60,layout:'grid'}).split('\n').map(l=>'  '.repeat(depth)+l).join('\n')+'\n'
  editor=new Editor({extensions:writingExtensions(),content:source,contentType:'markdown'})
  const output=editor.getMarkdown()
  expect(bodyMedia(output,2)).toEqual([{...media,widthPercent:60,layout:'grid'}])
  editor.commands.setContent(output,{contentType:'markdown'})
  expect(bodyMedia(editor.getMarkdown(),2)).toEqual([{...media,widthPercent:60,layout:'grid'}])
  expect(output).toContain(media.id)
 })

it.each([1,2,3])('undoes and redoes a visual private image insertion at list depth %i without dropping the original',depth=>{
 const parents=Array.from({length:depth},(_,i)=>'  '.repeat(i)+'- '+(i===depth-1?'@f 合成餐厅':'上层')).join('\n')
 const source=parents+'\n\n'+serializeMedia(media).split('\n').map(l=>'  '.repeat(depth)+l).join('\n')
 editor=new Editor({extensions:writingExtensions(),content:source,contentType:'markdown'})
 let at=0;editor.state.doc.descendants((node,pos)=>{if(node.isText&&node.text?.includes('合成餐厅'))at=pos+node.nodeSize})
 const second={...media,id:'22222222-2222-4222-8222-222222222222',widthPercent:30,layout:'grid' as const}
 editor.commands.insertContentAt(at,{type:'privateMedia',attrs:second})
 expect(bodyMedia(editor.getMarkdown(),2)).toEqual([second,media])
 expect(editor.commands.undo()).toBe(true);expect(bodyMedia(editor.getMarkdown(),2)).toEqual([media])
 expect(editor.commands.redo()).toBe(true);expect(bodyMedia(editor.getMarkdown(),2)).toEqual([second,media])
})

 it.each(['bulletList','orderedList'])('preserves image-only child list items in %s at three depths',kind=>{
  for(let depth=1;depth<=3;depth++){
   let branch:any={type:kind,content:[{type:'listItem',content:[{type:'paragraph'},{type:'privateMedia',attrs:media}]}]}
   for(let i=0;i<depth;i++)branch={type:kind,content:[{type:'listItem',content:[{type:'paragraph',content:[{type:'text',text:'@f 合成餐厅'}]},branch]}]}
   editor?.destroy();editor=new Editor({extensions:writingExtensions(),content:{type:'doc',content:[branch]}})
   const output=editor.getMarkdown()
   const prefix=kind==='orderedList'?'1. ':'- ',indent=prefix.length
   const expected=Array.from({length:depth},(_,i)=>' '.repeat(i*indent)+prefix+'@f 合成餐厅').join('\n')+'\n'+' '.repeat(depth*indent)+prefix+serializeMedia(media).split('\n').map((line,i)=>i?' '.repeat((depth+1)*indent)+line:line).join('\n')
   expect(output).toBe(expected)
   expect(bodyMedia(output,2)).toEqual([media])
   editor.commands.setContent(output,{contentType:'markdown'})
   expect(bodyMedia(editor.getMarkdown(),2),JSON.stringify({depth,kind,input:output,doc:editor.getJSON(),output:editor.getMarkdown()})).toEqual([media])
   expect(editor.state.doc.check()).toBeUndefined()
  }
 })

it('keeps JSON and closing lines aligned when a source list item starts with a private image',()=>{
 const block=serializeMedia(media).split('\n')
 const source='- @f 合成餐厅\n  - '+block[0]+'\n    '+block[1]+'\n    '+block[2]
 editor=new Editor({extensions:writingExtensions(),content:source,contentType:'markdown'})
 const output=editor.getMarkdown();expect(output).toContain('\n    {');expect(output).toContain('\n    :::');expect(bodyMedia(output,2)).toEqual([media]);expect(editor.state.doc.check()).toBeUndefined()
})
