// @vitest-environment jsdom
import { createApp,nextTick,type App } from 'vue'
import { createRouter,createMemoryHistory } from 'vue-router'
import { beforeEach,afterEach,expect,it,vi } from 'vitest'
import BlogView from './BlogView.vue'
import SiteAdmin from './SiteAdmin.vue'
import { fieldDisplay,navPath } from './types'
const api=vi.hoisted(()=>({request:vi.fn()}));vi.mock('../api',()=>api)
let app:App|undefined,root:HTMLDivElement,official={theme:'modern',mode:'system',revision:1}
const home={title:'私人杂志',description:'介绍',revision:1,modules:[{id:'hero',kind:'hero',title:'给日常留一点光',text:'空白也很好',enabled:true,count:6,layout:'grid2',record_ids:[],section_id:null,type_id:null},{id:'latest',kind:'latest',title:'最近故事',enabled:true,count:6,layout:'grid2',record_ids:[],section_id:null,type_id:null,items:[]}]}
const flush=async()=>{await new Promise(r=>setTimeout(r,0));await nextTick()}
function button(text:string){const b=Array.from(root.querySelectorAll('button')).find(b=>b.textContent?.trim()===text);if(!b)throw Error(text);return b}
async function mount(component:any,props:any={}){const router=createRouter({history:createMemoryHistory(),routes:[{path:'/:all(.*)*',component:{template:'<div />'}}]});await router.push('/');await router.isReady();app=createApp(component,props);app.use(router);app.mount(root);await flush();await flush()}
beforeEach(()=>{official={theme:'modern',mode:'system',revision:1};root=document.createElement('div');document.body.append(root);vi.spyOn(window,'confirm').mockReturnValue(true);api.request.mockReset().mockImplementation(async(path:string,options?:RequestInit)=>{
 if(path==='/blog/site')return {title:'私人杂志',description:'介绍',appearance:{...official},sections:[],navigation:[]}
 if(path==='/blog/home')return structuredClone(home)
 if(path==='/admin/status')return {features:{dynamic_blog:true}}
 if(path==='/admin/blog/sections'||path==='/admin/content/types')return []
 if(path.startsWith('/admin/content/records')||path.startsWith('/admin/archive/media'))return {items:[],total:0}
 if(path==='/admin/blog/navigation')return {revision:1,items:[]}
 if(path==='/admin/blog/layout')return structuredClone(home)
 if(path==='/admin/blog/appearance'){if(options){const {expected_revision,...v}=JSON.parse(String(options.body));official={...v,revision:expected_revision+1}}return {...official}}
 throw Error(path)
})})
afterEach(()=>{app?.unmount();app=undefined;root.remove();vi.restoreAllMocks()})
it('renders a content-first empty homepage without inventing records',async()=>{await mount(BlogView,{embedded:true});expect(root.querySelector('h1')?.textContent).toBe('给日常留一点光');expect(root.textContent).toContain('故事正在慢慢积累');expect(root.querySelector('.story-card')).toBeNull()})
it('keeps live theme preview separate from persisted appearance until Save',async()=>{await mount(SiteAdmin);button('外观设置').click();await flush();await flush();const radio=root.querySelector<HTMLInputElement>('input[value=editorial]')!;radio.checked=true;radio.dispatchEvent(new Event('change',{bubbles:true}));await nextTick();expect(root.querySelector('.blog')?.getAttribute('data-style')).toBe('editorial');expect(root.querySelector('.blog')?.getAttribute('data-theme')).toBe('modern');expect(official.theme).toBe('modern');expect(api.request.mock.calls.filter(([,o])=>o?.method==='PUT')).toHaveLength(0);button('保存外观').click();await flush();expect((official as any).style).toBe('editorial');expect(official.theme).toBe('modern');expect(root.textContent).toContain('已正式生效')})
it('cancels preview and resets defaults without writing automatically',async()=>{await mount(SiteAdmin);button('外观设置').click();await flush();await flush();const radio=root.querySelector<HTMLInputElement>('input[value=glass]')!;radio.checked=true;radio.dispatchEvent(new Event('change',{bubbles:true}));await nextTick();button('取消外观修改').click();await nextTick();expect(root.querySelector('.blog')?.getAttribute('data-theme')).toBe('modern');button('恢复默认主题（待保存）').click();expect(api.request.mock.calls.some(([,o])=>o?.method==='PUT')).toBe(false)})
it('renders all eight existing field kinds without exposing selection UUIDs or decimal rounding',()=>{const examples=[['short_text','文字','文字'],['long_text','长文字','长文字'],['markdown','**正文**','**正文**'],['integer',0,'0'],['decimal','900719925474.123456','900719925474.123456'],['date','2026-10-18','2026-10-18'],['select','uuid','可读选项'],['multiselect',['uuid'],'可读选项']];for(const [kind,value,expected] of examples)expect(fieldDisplay({kind,rules:{options:[{id:'uuid',label:'可读选项'}]}},value)).toBe(expected);expect(fieldDisplay({kind:'decimal'},null)).toBe('')})
it('maps only approved internal navigation targets',()=>{const s:any={id:'s',slug:'stable'};expect(navPath({kind:'section',section_id:'s'} as any,[s])).toBe('/sections/stable');expect(navPath({kind:'record',record_id:'r'} as any,[])).toBe('/posts/r');expect(navPath({kind:'page',page:'journals'} as any,[])).toBe('/stories')})
it('shows a friendly unavailable page without rendering untrusted HTML',async()=>{api.request.mockRejectedValue(Object.assign(Error('<script>bad()</script>'),{status:404}));await mount(BlogView,{embedded:true,target:'/posts/missing'});expect(root.textContent).toContain('这一页暂时留白');expect(root.querySelector('script')).toBeNull()})
it('switches dark mode without changing the theme or requesting a save',async()=>{await mount(BlogView,{embedded:true,preview:{theme:'glass',mode:'dark'}});expect(root.querySelector('.blog')?.getAttribute('data-mode')).toBe('dark');expect(root.querySelector('.blog')?.getAttribute('data-theme')).toBe('glass');expect(api.request.mock.calls.some(([,o])=>o?.method)).toBe(false)})
it('searches older library assets instead of restricting section covers to the first page',async()=>{await mount(SiteAdmin);button('新建栏目').click();await flush();const label=Array.from(root.querySelectorAll('label')).find(l=>l.textContent?.trim()==='搜索媒体库封面')!;const input=label.querySelector('input')!;input.value='旧照片';input.dispatchEvent(new Event('input',{bubbles:true}));await nextTick();button('查找待选封面').click();await flush();expect(api.request).toHaveBeenCalledWith('/admin/archive/media?page_size=100&q='+encodeURIComponent('旧照片'))})
it('edits an independent color, blocks invalid HEX, and cancels without changing the saved site',async()=>{
 await mount(SiteAdmin);button('外观设置').click();await flush();await flush()
 const inherit=root.querySelector<HTMLInputElement>('[aria-label="页面背景跟随主题"]')!;inherit.click();await nextTick()
 const input=root.querySelector<HTMLInputElement>('[aria-label="页面背景 HEX"]')!;expect(input.disabled).toBe(false)
 input.value='#f0eedd';input.dispatchEvent(new Event('input',{bubbles:true}));await flush()
 expect((root.querySelector('.blog') as HTMLElement).style.getPropertyValue('--reader-page-background')).toBe('#f0eedd')
 expect(api.request.mock.calls.some(([,o])=>o?.method==='PUT')).toBe(false)
 input.value='#nope';input.dispatchEvent(new Event('input',{bubbles:true}));await nextTick();await nextTick()
 expect((button('保存外观') as HTMLButtonElement).disabled).toBe(true)
 button('取消外观修改').click();await flush();expect((button('保存外观') as HTMLButtonElement).disabled).toBe(false)
 expect((root.querySelector('.blog') as HTMLElement).style.getPropertyValue('--reader-page-background')).toBe('')
})
it('saves colors independently per theme/mode, clears the current theme and restores defaults as a draft',async()=>{
 await mount(SiteAdmin);button('外观设置').click();await flush();await flush()
 const set=async(label:string,value:string)=>{root.querySelector<HTMLInputElement>(`[aria-label="${label}跟随主题"]`)!.click();await nextTick();const input=root.querySelector<HTMLInputElement>(`[aria-label="${label} HEX"]`)!;input.value=value;input.dispatchEvent(new Event('input',{bubbles:true}));await flush()}
 await set('标题','#ffffff');await set('页面背景','#ffffff');expect(root.textContent).toContain('文字对比度提醒')
 button('保存外观').click();await flush();expect((official as any).colors.modern.light.heading_text).toBe('#ffffff')
 const select=root.querySelector<HTMLSelectElement>('[aria-label="编辑颜色模式"]')!;select.value='dark';select.dispatchEvent(new Event('change',{bubbles:true}));await flush()
 await set('标题','#ddeeff');expect(root.querySelector('.blog')?.getAttribute('data-mode')).toBe('dark')
 button('保存外观').click();await flush();expect(official.mode).toBe('system');expect((official as any).colors.modern.light.heading_text).toBe('#ffffff');expect((official as any).colors.modern.dark.heading_text).toBe('#ddeeff')
 button('清除当前主题全部颜色覆盖（待保存）').click();await flush();expect((official as any).colors.modern).toBeDefined();expect((root.querySelector('.blog') as HTMLElement).style.getPropertyValue('--reader-heading-text')).toBe('')
 button('取消外观修改').click();await flush();button('恢复默认主题（待保存）').click();await flush();expect((official as any).colors.modern).toBeDefined();button('保存外观').click();await flush();expect((official as any).colors.modern.dark.heading_text).toBe('#ddeeff');expect((official as any).combination_colors['modern-soft'].celadon).toEqual({light:{},dark:{}})
})
it('offers both Modern Soft palettes while retaining old soft identity and cancel semantics',async()=>{
 await mount(SiteAdmin);button('外观设置').click();await flush();await flush()
 for(const theme of ['celadon','lilac']){
  const radio=root.querySelector<HTMLInputElement>(`input[value=${theme}]`)!;radio.checked=true;radio.dispatchEvent(new Event('change',{bubbles:true}));await flush()
  expect(root.querySelector('.blog')?.getAttribute('data-palette')).toBe(theme);expect(root.querySelector('.blog')?.getAttribute('data-theme')).toBe('modern')
  expect(root.querySelectorAll('.theme-ornament svg')).toHaveLength(1)
  expect(root.querySelector('.botanical-celadon')).not.toBeNull();expect(root.querySelector('.botanical-lilac')).not.toBeNull()
  expect(root.querySelector('.theme-ornament')?.getAttribute('aria-hidden')).toBe('true')
  expect(official.theme).toBe('modern')
 }
 expect(root.textContent).toContain('晨雾青瓷');expect(root.textContent).toContain('丁香奶油')
 button('取消外观修改').click();await flush();expect(root.querySelector('.blog')?.getAttribute('data-theme')).toBe('modern')
})

it.each(['modern','editorial','soft','glass'])('renders anniversary home content within the existing %s theme in both modes',async theme=>{
 const fallback=api.request.getMockImplementation()!
 const events=[{id:'today',name:'今天的合成日子',date:'2026-11-13',days_left:0,years:2},{id:'next',name:'将来的合成日子',date:'2026-11-20',days_left:7,years:3}]
 api.request.mockImplementation((path,o)=>path==='/blog/home'?Promise.resolve({...structuredClone(home),modules:[{...home.modules[1],kind:'anniversary_calendar',events,show_countdown:false,show_years:false}]}):fallback(path,o))
 for(const mode of ['light','dark']){
  await mount(BlogView,{embedded:true,preview:{theme,mode}})
  expect(root.querySelector('.blog')?.getAttribute('data-mode')).toBe(mode)
  expect(root.textContent).toContain('今天');expect(root.textContent).not.toContain('剩余 0 天')
  expect(root.textContent).not.toContain('还有 7 天');expect(root.textContent).not.toContain('周年')
  expect(root.querySelector('a[href="/calendar?event=today"]')).not.toBeNull()
  expect(root.querySelector('a[href="/calendar"]')).not.toBeNull()
  app!.unmount();app=undefined;root.innerHTML=''
 }
})
