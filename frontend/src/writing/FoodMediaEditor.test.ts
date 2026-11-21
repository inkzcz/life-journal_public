// @vitest-environment jsdom
import {createApp,h,nextTick,ref,type App} from 'vue'
import {afterEach,it,expect,vi} from 'vitest'
import {bodyTree,compactBody,serializeMedia,mediaBlock,type MediaBlock} from './body'
import ArticleBody from '../reading/ArticleBody.vue'
import BodyEditor from './BodyEditor.vue'
import {travelFields} from './travelDates'
import {newField} from '../admin/types'
const api=vi.hoisted(()=>({request:vi.fn(),uploadImage:vi.fn()}));vi.mock('../api',()=>api)
vi.mock('../admin/PrivatePreview.vue',()=>({default:{props:['id','alt'],template:'<img :data-media-id="id" :alt="alt"/>'}}))
const image=(n:number,patch:Partial<MediaBlock>={}):MediaBlock=>({id:`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`,alt:'合成图'+n,caption:'',width:960,align:'center',...patch})
const source=(n:number)=>Array.from({length:n},(_,i)=>serializeMedia(image(i+1))).join('\n\n')
let app:App|undefined,root:HTMLElement|undefined
const flush=async()=>{for(let n=0;n<5;n++){await Promise.resolve();await nextTick()}}
afterEach(()=>{app?.unmount();root?.remove();vi.restoreAllMocks();vi.clearAllMocks()})
it.each([2,3,4,5,8])('groups %i consecutive default photos without changing the source',n=>{
 const body=source(n),grouped=compactBody(bodyTree(body,2));expect(grouped).toHaveLength(1);expect(grouped[0]?.gallery).toHaveLength(n);expect(source(n)).toBe(body)
})
it('preserves single, explicit percentage/alignment/width and text barriers',()=>{
 for(const patch of [{layout:'single' as const},{widthPercent:60},{width:480},{align:'right' as const}]){
  const nodes=compactBody(bodyTree(serializeMedia(image(1,patch))+'\n\n'+serializeMedia(image(2)),2));expect(nodes.some(n=>n.gallery)).toBe(false)
 }
 expect(compactBody(bodyTree(source(2)+'\n\n正文不能跨过\n\n'+source(2),2)).filter(n=>n.gallery)).toHaveLength(2)
 expect(compactBody(bodyTree(source(1),2))[0]?.media?.id).toBe(image(1).id)
 expect(mediaBlock({...image(1),layout:'url(javascript:bad)'})).toBeNull()
})
it('renders a real compact component with keyboard lightbox in authored order',async()=>{
 // jsdom has no native dialog; the real browser suite exercises showModal itself.
 Object.defineProperty(HTMLDialogElement.prototype,'showModal',{configurable:true,value:function(this:HTMLDialogElement){this.setAttribute('open','')}})
 Object.defineProperty(HTMLDialogElement.prototype,'close',{configurable:true,value:function(this:HTMLDialogElement){this.removeAttribute('open')}})
 api.request.mockResolvedValue({is_admin:false});root=document.createElement('div');document.body.append(root);app=createApp(ArticleBody,{source:source(4),format:2,namespace:'grid'});app.mount(root);await flush()
 expect(root.querySelector('.inline-media-grid')?.getAttribute('data-count')).toBe('4')
 const buttons=root.querySelectorAll<HTMLButtonElement>('.body-photo-button');expect(buttons).toHaveLength(4);buttons[1]!.click();await flush()
 const dialog=root.querySelector('dialog')!;expect(dialog.hasAttribute('open')).toBe(true);expect(dialog.querySelector('img')?.dataset.mediaId).toBe(image(2).id)
 dialog.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}));await flush();expect(dialog.querySelector('img')?.dataset.mediaId).toBe(image(3).id)
 expect(dialog.textContent).not.toContain('下载原图')
})
it('keeps source insertion bookmark while sticky toolbar and media search take focus',async()=>{
 vi.spyOn(window,'scrollTo').mockImplementation(()=>{})
 api.request.mockImplementation(async(path:string)=>path.includes('folders')?[]:{items:[{...image(9),filename:'synthetic.jpg'}],total:1})
 const text=ref('|表格|\n|---|\n\n前段\n中间\n后段'),at=text.value.indexOf('中间')
 root=document.createElement('main');root.className='writing-page';document.body.append(root)
 const save=document.createElement('div');save.className='workspace-save';save.style.position='sticky';save.getBoundingClientRect=()=>({top:0,bottom:88,height:88,left:0,right:600,width:600,x:0,y:0,toJSON(){}});root.append(save)
 const mount=document.createElement('div');root.append(mount);app=createApp({render:()=>h(BodyEditor,{modelValue:text.value,format:2,'onUpdate:modelValue':(v:string)=>text.value=v})});app.mount(mount);await flush()
 window.dispatchEvent(new Event('scroll'));await flush();expect(root.querySelector<HTMLElement>('.writing-toolbar')?.style.top).toBe('88px')
 const textarea=root.querySelector('textarea')!;textarea.focus();textarea.setSelectionRange(at,at)
 Array.from(root.querySelectorAll('button')).find(b=>b.textContent==='从媒体库插图')!.click();await flush()
 const search=root.querySelector<HTMLInputElement>('.inline-media-picker input')!;search.focus();search.value='合成';search.dispatchEvent(new Event('input',{bubbles:true}))
 root.querySelector<HTMLButtonElement>('.picker-grid button')!.click();await flush()
 expect(text.value).not.toContain(image(9).id)
 Array.from(root.querySelectorAll('button')).find(b=>b.textContent==='确认插入 1 张')!.click();await flush()
 expect(text.value.indexOf(image(9).id)).toBeGreaterThan(text.value.indexOf('前段'));expect(text.value.indexOf(image(9).id)).toBeLessThan(text.value.indexOf('中间'));expect(text.value).toContain('后段')
})


it('keeps renamed food semantics separate from legacy travel date heuristics',()=>{
 const foodDate={...newField(),id:'meal',kind:'date' as const,purpose:'food_date',name:'出发日期'}
 const foodShop={...newField(),id:'shop',purpose:'food_shop',name:'住宿'}
 const actualTrip={...newField(),id:'trip',kind:'date' as const,name:'旅行开始日期'}
 const result=travelFields([foodDate,foodShop,actualTrip]);expect(result.start?.id).toBe('trip');expect(result.lodging).toEqual([])
})

it('selects multiple private photos before confirmation, preserves order, and keeps the side workspace open',async()=>{
 vi.spyOn(window,'scrollTo').mockImplementation(()=>{})
 const photos=[{...image(7),filename:'很长的合成文件名.jpg'},{...image(8),filename:'second.jpg'}]
 api.request.mockImplementation(async(path:string)=>path.includes('folders')?[]:{items:photos,total:2})
 const text=ref('|原文|\n|---|\n尾声');root=document.createElement('main');document.body.append(root)
 app=createApp({render:()=>h(BodyEditor,{modelValue:text.value,format:2,'onUpdate:modelValue':(v:string)=>text.value=v})});app.mount(root);await flush()
 const area=root.querySelector('textarea')!;area.focus();area.setSelectionRange(0,0)
 Array.from(root.querySelectorAll('button')).find(b=>b.textContent==='从媒体库插图')!.click();await flush()
 const choices=root.querySelectorAll<HTMLButtonElement>('.picker-grid button[aria-pressed]');choices[0]!.click();choices[1]!.click();await flush()
 expect(text.value).not.toContain(photos[0]!.id);expect(choices[0]!.getAttribute('aria-pressed')).toBe('true')
 Array.from(root.querySelectorAll('button')).find(b=>b.textContent==='确认插入 2 张')!.click();await flush()
 expect(text.value.indexOf(photos[0]!.id)).toBeLessThan(text.value.indexOf(photos[1]!.id));expect(text.value).toContain('|原文|');expect(text.value).toContain('尾声')
 expect((root.querySelector('.editor-tools') as HTMLElement).style.display).not.toBe('none')
 expect(root.querySelector('[title="很长的合成文件名.jpg"]')).not.toBeNull()
})

it('does not treat IME inside the media search panel as composition in the article body',async()=>{
 api.request.mockImplementation(async(path:string)=>path.includes('folders')?[]:{items:[],total:0})
 const pending=vi.fn(),body=vi.fn();root=document.createElement('main');document.body.append(root)
 app=createApp(BodyEditor,{modelValue:'原正文',format:2,onPending:pending,'onUpdate:modelValue':body});app.mount(root);await flush()
 Array.from(root.querySelectorAll('button')).find(b=>b.textContent==='从媒体库插图')!.click();await flush()
 const search=root.querySelector<HTMLInputElement>('input[type=search]')!;search.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true}));search.value='中文查询';search.dispatchEvent(new Event('input',{bubbles:true}));search.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true}));await flush()
 expect(body).not.toHaveBeenCalled();expect(pending.mock.calls.some(([v])=>v===true)).toBe(false)
})

it('tracks a new source selection while the picker stays open and preserves it after search steals focus',async()=>{
 vi.spyOn(window,'scrollTo').mockImplementation(()=>{})
 api.request.mockImplementation(async(path:string)=>path.includes('folders')?[]:{items:[{...image(9),filename:'synthetic.jpg'}],total:1})
 const text=ref('|原文|\n|---|\n\n第一段\n\n第二段\n\n第三段')
 root=document.createElement('main');document.body.append(root)
 app=createApp({render:()=>h(BodyEditor,{modelValue:text.value,format:2,'onUpdate:modelValue':(v:string)=>text.value=v})});app.mount(root);await flush()
 const area=root.querySelector('textarea')!,click=(label:string)=>Array.from(root!.querySelectorAll('button')).find(b=>b.textContent===label)!.click()
 area.focus();area.setSelectionRange(text.value.indexOf('第一段'),text.value.indexOf('第一段'));click('从媒体库插图');await flush()
 const select=()=>root!.querySelector<HTMLButtonElement>('.picker-grid button[aria-pressed]')!.click()
 select();await flush();click('确认插入 1 张');await flush()
 const before=text.value.lastIndexOf('第二段');area.focus();area.setSelectionRange(before,before);area.dispatchEvent(new Event('select',{bubbles:true}));await flush()
 root.querySelector<HTMLInputElement>('input[type=search]')!.focus();select();await flush();click('确认插入 1 张');await flush()
 const hits=[...text.value.matchAll(new RegExp(image(9).id,'g'))].map(m=>m.index!)
 expect(hits).toHaveLength(2);expect(hits[0]).toBeLessThan(text.value.indexOf('第一段'));expect(hits[1]).toBeGreaterThan(text.value.indexOf('第一段'));expect(hits[1]).toBeLessThan(text.value.indexOf('第二段'))
 const footer=root.querySelector('.editor-tools-actions')!;expect(footer.closest('.editor-tools-scroll')).toBeNull();expect(footer.textContent).toContain('已选择 0 张')
})
