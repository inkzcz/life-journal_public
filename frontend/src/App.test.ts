// @vitest-environment jsdom
import { createApp, nextTick, type App as VueApp } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './legacy/JournalFixture.vue'

const api=vi.hoisted(()=>({request:vi.fn(),privateImage:vi.fn()}))
vi.mock('./api',()=>api)
const journal={id:1,title:'第一篇',content:'# 私人正文',entry_date:'2026-01-01',category:'日常',tags:['阅读'],updated_at:'2026-01-01T00:00:00Z'}
let app:VueApp, root:HTMLDivElement
const flush=async()=>{await new Promise(resolve=>setTimeout(resolve,0));await nextTick()}
function button(text:string){
  const found=Array.from(root.querySelectorAll('button')).find(el=>el.textContent?.trim()===text)
  if(!found)throw new Error('Missing button '+text)
  return found
}
async function input(el:HTMLInputElement|HTMLTextAreaElement,value:string){el.value=value;el.dispatchEvent(new Event('input',{bubbles:true}));await nextTick()}
async function open(){button('第一篇2026-01-01 · 日常#阅读').click();await flush()}
function defaultRequest(path:string,options?:RequestInit):unknown{
  if(path==='/auth/me')return {username:'admin'}
  if(path==='/journals/filters')return {categories:['日常'],tags:['阅读']}
  if(path.startsWith('/journals/page?'))return {items:[journal,{...journal,id:2,title:'第二篇'}],total:21,page:1,page_size:20}
  if(path.endsWith('/media'))return []
  if(options?.method==='PUT'||options?.method==='POST')return {...journal,...JSON.parse(String(options.body))}
  if(path==='/journals/1')return journal
  if(path==='/journals/2')return {...journal,id:2,title:'第二篇'}
  return {ok:true}
}
beforeEach(async()=>{
  api.request.mockReset().mockImplementation(async(...args:Parameters<typeof defaultRequest>)=>defaultRequest(...args))
  api.privateImage.mockReset()
  vi.spyOn(window,'confirm').mockReturnValue(true)
  root=document.createElement('div');document.body.append(root)
  app=createApp(App);app.mount(root);await flush()
})
afterEach(()=>{app.unmount();root.remove();vi.restoreAllMocks()})

describe('日记浏览与编辑',()=>{
  it('warns that deleting a legacy diary bypasses trash',async()=>{await open();vi.mocked(window.confirm).mockReturnValue(false);button('删除日记').click();await flush();expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('旧版日记不进入回收站'));expect(api.request.mock.calls.some(([,o])=>o?.method==='DELETE')).toBe(false)})
  it('uses paged summaries and fetches fresh details before rendering Markdown',async()=>{
    expect(api.request).toHaveBeenCalledWith('/journals/page?page=1&page_size=20')
    await open()
    expect(api.request).toHaveBeenCalledWith('/journals/1')
    expect(root.querySelector('.markdown h1')?.textContent).toBe('私人正文')
    expect(root.querySelector('.editor textarea')).toBeNull()
    button('编辑日记').click();await nextTick()
    expect(root.querySelector('textarea')?.value).toBe('# 私人正文')
  })
  it('asks before abandoning edits and keeps the draft when declined',async()=>{
    await open();button('编辑日记').click();await nextTick()
    await input(root.querySelector('textarea')!,'还没有保存')
    vi.mocked(window.confirm).mockReturnValue(false)
    button('+ 新建').click();await nextTick()
    expect(window.confirm).toHaveBeenCalled()
    expect(root.querySelector('textarea')?.value).toBe('还没有保存')
    const event=new Event('beforeunload',{cancelable:true});window.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
  })
  it('cancels editing by rereading persisted content',async()=>{
    await open();button('编辑日记').click();await nextTick()
    await input(root.querySelector('textarea')!,'草稿')
    button('取消编辑').click();await flush()
    expect(root.querySelector('.markdown h1')?.textContent).toBe('私人正文')
  })
  it('prevents duplicate saves and sends normalized category, tags and date',async()=>{
    let resolveSave!:(value:unknown)=>void
    api.request.mockImplementation(async(path:string,options?:RequestInit)=>{
      if(options?.method==='POST')return new Promise(resolve=>{resolveSave=resolve})
      return defaultRequest(path,options)
    })
    const fields=root.querySelectorAll<HTMLInputElement>('.editor input')
    await input(fields[0]!,'新日记');await input(fields[1]!,'2026-03-02');await input(fields[2]!,'日常');await input(fields[3]!,'阅读， 阅读, 心情')
    const form=root.querySelector('.editor form')!
    form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await nextTick()
    form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await nextTick()
    const calls=api.request.mock.calls.filter(([,o])=>o?.method==='POST')
    expect(calls).toHaveLength(1)
    expect(JSON.parse(calls[0]![1].body)).toMatchObject({entry_date:'2026-03-02',category:'日常',tags:['阅读','心情']})
    resolveSave({...journal,title:'新日记'});await flush()
    expect(root.textContent).toContain('日记已保存')
  })
  it('retains draft after save failure',async()=>{
    api.request.mockImplementation(async(path:string,options?:RequestInit)=>{
      if(options?.method==='POST')throw new Error('连接失败')
      return defaultRequest(path,options)
    })
    await input(root.querySelector<HTMLInputElement>('.editor input')!,'草稿标题')
    await input(root.querySelector('textarea')!,'不要丢失')
    root.querySelector('.editor form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await flush()
    expect(root.querySelector('textarea')?.value).toBe('不要丢失')
    expect(root.querySelector('[role=alert]')?.textContent).toContain('连接失败')
  })
  it('ignores stale detail responses when switching quickly',async()=>{
    let resolveFirst!:(value:unknown)=>void
    api.request.mockImplementation(async(path:string,options?:RequestInit)=>{
      if(path==='/journals/1')return new Promise(resolve=>{resolveFirst=resolve})
      return defaultRequest(path,options)
    })
    button('第一篇2026-01-01 · 日常#阅读').click();await flush()
    button('第二篇2026-01-01 · 日常#阅读').click();await flush()
    resolveFirst(journal);await flush()
    expect(root.querySelector('.detail-heading h2')?.textContent).toBe('第二篇')
  })
  it('paginates and resets to page one when applying search',async()=>{
    button('下一页').click();await flush()
    expect(api.request).toHaveBeenCalledWith('/journals/page?page=2&page_size=20')
    await input(root.querySelector<HTMLInputElement>('input[type=search]')!,'雨天')
    root.querySelector('.filters')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await flush()
    expect(api.request).toHaveBeenCalledWith('/journals/page?page=1&page_size=20&q=%E9%9B%A8%E5%A4%A9')
  })
  it('clears private content after session expiry',async()=>{
    await open();window.dispatchEvent(new Event('session-expired'));await flush()
    expect(root.textContent).toContain('登录私人空间')
    expect(root.textContent).not.toContain('私人正文')
    expect(root.querySelector('.layout')).toBeNull()
  })
})

describe('动态后台入口',()=>{
  it('keeps legacy journals visible when dynamic features are disabled',()=>{
    expect(root.textContent).not.toContain('内容管理后台')
    expect(root.textContent).toContain('我的日记')
  })
  it('shows the entry only after Admin status explicitly enables the feature',async()=>{
    app.unmount()
    api.request.mockImplementation(async(path:string,options?:RequestInit)=>path==='/admin/status'?{is_admin:true,features:{dynamic_blog:true}}:defaultRequest(path,options))
    app=createApp(App);app.mount(root);await flush()
    expect(button('内容管理后台')).toBeDefined()
    window.dispatchEvent(new Event('session-expired'));await flush()
    expect(root.textContent).not.toContain('内容管理后台')
    expect(root.textContent).toContain('登录私人空间')
  })
})

it('lets a later editor listener retain unconfirmed input before the expiry default runs',async()=>{
 await open();const retain=(e:Event)=>e.preventDefault();window.addEventListener('session-expired',retain,true)
 try{window.dispatchEvent(new Event('session-expired',{cancelable:true}));await flush();expect(root.textContent).toContain('私人正文');expect(root.querySelector('.layout')).not.toBeNull()}finally{window.removeEventListener('session-expired',retain,true)}
 window.dispatchEvent(new Event('session-expired',{cancelable:true}));await flush();expect(root.textContent).toContain('登录私人空间');expect(root.textContent).not.toContain('私人正文')
})
