// @vitest-environment jsdom
import {it,expect,vi,afterEach} from 'vitest'
import {createApp,h,nextTick,ref} from 'vue'
import ArticleBody from './ArticleBody.vue'
import {serializeEntry,type Entry} from '../writing/entries'
import {serializeMedia} from '../writing/body'
import {saved,defaults} from '../presentation/typography'
vi.mock('../api',()=>({request:vi.fn(async()=>({...defaults()}))}))
const card=(n:number,kind:Entry['kind']='f'):Entry=>({id:`10000000-0000-0000-0000-${String(n).padStart(12,'0')}`,kind,name:'同名',fields:kind==='t'?{service_number:'G8533',departure:'重庆',destination:'成都'}:{review:'完整感受'},media_ids:[]})
let dispose=()=>{}
afterEach(()=>{dispose();saved.value=defaults();vi.restoreAllMocks()})
async function mount(source:string,format=2){const body=ref(source),namespace=ref('test');const root=document.createElement('div');document.body.append(root);const app=createApp({render:()=>h(ArticleBody,{source:body.value,namespace:namespace.value,format,previewMedia:[1,2].map(n=>({id:'20000000-0000-0000-0000-'+String(n).padStart(12,'0'),url:'/api/library-media/20000000-0000-0000-0000-'+String(n).padStart(12,'0')+'/preview'}))})});app.mount(root);dispose=()=>{app.unmount();root.remove()};await nextTick();await nextTick();await nextTick();return {root,body,namespace}}
async function click(root:HTMLElement,text:string){const button=Array.from(root.querySelectorAll('button')).find(b=>b.textContent?.trim()===text)!;expect(button).toBeTruthy();button.click();await nextTick();return button}
it('keeps document order, compacts inline semantic cards, and opens a keyboard accessible modal without saving',async()=>{
 if(!HTMLDialogElement.prototype.showModal)Object.defineProperty(HTMLDialogElement.prototype,'showModal',{configurable:true,value:function(){}})
 if(!HTMLDialogElement.prototype.close)Object.defineProperty(HTMLDialogElement.prototype,'close',{configurable:true,value:function(){}})
 vi.spyOn(HTMLDialogElement.prototype,'showModal').mockImplementation(function(this:HTMLDialogElement){this.open=true})
 vi.spyOn(HTMLDialogElement.prototype,'close').mockImplementation(function(this:HTMLDialogElement){this.open=false})
 const transport=card(1,'t');transport.media_ids=['20000000-0000-0000-0000-000000000001']
 const source=['之前',serializeEntry(transport),'之后',serializeMedia({id:'20000000-0000-0000-0000-000000000002',alt:'正文图',caption:'',width:960,align:'center'})].join('\n\n')
 const {root,body}=await mount(source)
 expect(root.textContent!.indexOf('之前')).toBeLessThan(root.textContent!.indexOf('G8533'))
 await click(root,'纯正文');expect(root.querySelector('.entry-inline')?.textContent).toContain('重庆 → 成都');expect(root.querySelectorAll('img')).toHaveLength(1)
 const inline=root.querySelector<HTMLButtonElement>('.entry-inline')!;expect(inline.tagName).toBe('BUTTON');expect(inline.getAttribute('aria-haspopup')).toBe('dialog');inline.focus();inline.click();await nextTick();await nextTick()
 expect(root.querySelector<HTMLDialogElement>('.entry-reader-dialog')?.open).toBe(true);expect(document.activeElement?.textContent).toBe('关闭卡片');expect(root.querySelector<HTMLDialogElement>('.entry-reader-dialog')?.textContent).toContain('G8533')
 root.querySelector<HTMLDialogElement>('.entry-reader-dialog')!.dispatchEvent(new Event('cancel',{cancelable:true}));await nextTick();expect(root.querySelector<HTMLDialogElement>('.entry-reader-dialog')?.open).toBe(false);expect(document.activeElement).toBe(inline);expect(body.value).toBe(source)
 const {request}=await import('../api');expect(vi.mocked(request).mock.calls.every(call=>!call[1])).toBe(true)
})
it('counts only active current-body cards, filters all six kinds and jumps by UUID with repeated names',async()=>{
 const cards=['l','f','m','s','g','t'].map((kind,i)=>card(i+1,kind as Entry['kind']))
 const inactive=serializeEntry(card(99)),source=cards.map(serializeEntry).join('\n\n')+'\n\n```md\n'+inactive+'\n```\n\n> '+inactive.replaceAll('\n','\n> ')+'\n\n@f 历史文本标记'
 const {root,body}=await mount(source)
 const scroll=vi.fn();HTMLElement.prototype.scrollIntoView=scroll
 await click(root,'卡片汇总');expect(root.querySelector('[aria-label="卡片分类"]')?.textContent).toContain('全部 (6)');expect(root.querySelectorAll('.summary-entry')).toHaveLength(6)
 await click(root,'交通 (1)');expect(root.querySelectorAll('.summary-entry')).toHaveLength(1);await click(root,'定位至正文 · 同名');await nextTick()
 expect(root.querySelector('[aria-label="文章阅读模式"] [aria-pressed=true]')?.textContent).toBe('完整阅读');expect(scroll).toHaveBeenCalledOnce();expect(document.activeElement?.id).toBe('entry-'+cards[5]!.id)
 body.value=serializeEntry(cards[0]!);await nextTick();await click(root,'卡片汇总');expect(root.querySelector('[aria-label="卡片分类"]')?.textContent).toBe('全部 (1)地点 (1)');expect(root.querySelectorAll('.summary-entry')).toHaveLength(1)
 body.value='正文：历史修订已移除卡片';await nextTick();expect(root.querySelector('[aria-label="文章阅读模式"]')).toBeNull();expect(root.querySelectorAll('.summary-entry')).toHaveLength(0)
})
it('keeps legacy formats and code markers inert and applies only confirmed default preference',async()=>{
 saved.value={...defaults(),reader_mode:'plain'};const {root}=await mount(serializeEntry(card(1)));expect(root.querySelector('.entry-inline')).not.toBeNull();await click(root,'完整阅读');expect(saved.value.reader_mode).toBe('plain')
 dispose();const legacy=await mount(serializeEntry(card(2)),1);expect(legacy.root.querySelector('[aria-label="文章阅读模式"]')).toBeNull()
})

it('derives nested list cards from the same body tree in document order',async()=>{
 const nested=serializeEntry(card(2,'m')).split('\n').map(line=>'  '+line).join('\n')
 const {root}=await mount(serializeEntry(card(1,'l'))+'\n\n- 叙事列表\n\n'+nested+'\n\n'+serializeEntry(card(3,'g')))
 await click(root,'卡片汇总');expect(root.querySelector('[aria-label="卡片分类"]')?.textContent).toContain('全部 (3)')
 expect(Array.from(root.querySelectorAll('.summary-entry [id]')).map(node=>node.id).filter(id=>id.startsWith('entry-'))).toEqual([1,2,3].map(n=>'entry-'+card(n).id))
})
