// @vitest-environment jsdom
import {createApp,h,nextTick,ref,type App} from 'vue'
import {it,expect,vi,afterEach} from 'vitest'
import {Editor} from '@tiptap/core'
import {renderMarkdown} from '../markdown'
import {visualCompatible,serializeMedia,mediaStyle} from './body'
import {writingExtensions} from './extensions'
import BodyEditor from './BodyEditor.vue'
const api=vi.hoisted(()=>({request:vi.fn(),uploadImage:vi.fn()}));vi.mock('../api',()=>api)
let app:App|undefined,root:HTMLElement|undefined
const settle=async()=>{await new Promise(r=>setTimeout(r,0));await nextTick();await nextTick()}
afterEach(()=>{app?.unmount();root?.remove();vi.clearAllMocks();vi.restoreAllMocks()})
it('renders place icons safely and preserves code examples',()=>{
 const html=renderMarkdown('@l 汉源 @f 牛肉\n\n@h 合成酒店 {#place:11111111-1111-4111-8111-111111111111}\n\n`@s 示例景点`')
 expect(html).toContain('汉源');expect(html).toContain('牛肉');expect(html).toContain('<svg');expect(html).not.toContain('@l');expect(html).not.toContain('{#place:');expect(html).toContain('<code>@s 示例景点</code>')
 const safe=document.createElement('template');safe.innerHTML=renderMarkdown('@f <img src=x onerror=alert(1)>');expect(safe.content.querySelector('img,[onerror],script')).toBeNull();expect(safe.content.textContent).toContain('<img')
})
it('accepts literal reserved syntax inside code without enabling lossy task lists or tables',()=>{
 expect(visualCompatible('```\n:::lj-media-v2\n{}\n:::\n```')).toBe(true)
 expect(visualCompatible('## 10月3日\n\n- @l 汉源 @f 合成餐馆\n  - 说明')).toBe(true)
 expect(visualCompatible('- [x] 任务')).toBe(false)
 expect(visualCompatible('|a|\n|---|\n|b|')).toBe(false)
})
it('round trips percentage sizes and readable places',()=>{
 const m={id:'11111111-1111-4111-8111-111111111111',alt:'合成照片',caption:'说明',width:960,widthPercent:60,align:'right' as const}
 const e=new Editor({extensions:writingExtensions(),content:'@l 汉源\n\n'+serializeMedia(m),contentType:'markdown'})
 expect(e.getMarkdown()).toContain('"widthPercent":60');expect(e.getMarkdown()).toContain('@l 汉源');expect(mediaStyle(m).width).toBe('60%');e.destroy()
})
it('source upload inserts at cursor and preserves the unsupported original table',async()=>{
 api.request.mockImplementation(async(path:string)=>path==='/admin/archive/folders'?[]:{items:[],total:0});api.uploadImage.mockImplementation(async(_p,_f,_k,_s,progress)=>{progress(65);return {id:'11111111-1111-4111-8111-111111111111',filename:'synthetic.png',alt:'合成'}})
 vi.spyOn(window,'scrollTo').mockImplementation(()=>{})
 const text=ref('|原文|\n|---|\n|保留|\n\n末尾'),format=ref(1)
 root=document.createElement('div');document.body.append(root);app=createApp({render:()=>h(BodyEditor,{modelValue:text.value,format:format.value,'onUpdate:modelValue':(v:string)=>text.value=v,'onUpdate:format':(v:number)=>format.value=v})});app.mount(root);await settle()
 const source=root.querySelector('textarea')!;source.setSelectionRange(source.value.length,source.value.length)
 expect(Array.from(root.querySelectorAll('button')).find(b=>b.textContent==='上传图片')).toBeTruthy()
 const input=root.querySelector<HTMLInputElement>('input[type=file]')!;Object.defineProperty(input,'files',{value:[new File(['synthetic'],'synthetic.png',{type:'image/png'})]});input.dispatchEvent(new Event('change',{bubbles:true}));await settle()
 expect(api.uploadImage).toHaveBeenCalledOnce();expect(text.value).toContain('|原文|\n|---|\n|保留|');expect(text.value).toContain(':::lj-media-v1');expect(format.value).toBe(2);expect(root.textContent).toContain('已上传')
})

it('never emits a hidden visual document when busy/save toggles disabled in source mode',async()=>{
 const disabled=ref(false),update=vi.fn(),original='|原文|\n|---|\n|不能被覆盖|'
 api.request.mockImplementation(async(path:string)=>path==='/admin/archive/folders'?[]:{items:[],total:0})
 root=document.createElement('div');document.body.append(root);app=createApp({render:()=>h(BodyEditor,{modelValue:original,disabled:disabled.value,'onUpdate:modelValue':update})});app.mount(root);await settle()
 disabled.value=true;await settle();disabled.value=false;await settle()
 expect(update).not.toHaveBeenCalled();expect(root.querySelector('textarea')?.value).toBe(original)
})

it('renders compact and bracketed marks without consuming following prose or parsing code and URLs',()=>{
 const html=renderMarkdown("途经@l汉源县 @f[Joe's Pizza] 然后出发\n\n`@s不解析`\n\nhttps://example.com/@h酒店")
 const doc=document.createElement('template');doc.innerHTML=html
 expect(Array.from(doc.content.querySelectorAll('.lj-place-mark')).map(e=>e.textContent)).toEqual(['汉源县',"Joe's Pizza"])
 expect(doc.content.textContent).toContain('然后出发');expect(doc.content.textContent).toContain('@s不解析')
})
