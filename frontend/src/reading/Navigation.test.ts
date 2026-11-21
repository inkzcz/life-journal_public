// @vitest-environment jsdom
import { createApp,h,nextTick } from 'vue'
import { createRouter,createMemoryHistory,RouterView } from 'vue-router'
import { it,expect,vi } from 'vitest'
import BlogView from '../blog/BlogView.vue'
import { blankSite } from '../blog/types'
const api=vi.hoisted(()=>({request:vi.fn()}));vi.mock('../api',()=>api)
it('renders the article while optional neighbors wait and ignores a late response for another post',async()=>{
 let resolve!:(value:any)=>void;const pending=new Promise(r=>resolve=r)
 vi.stubGlobal('matchMedia',()=>({matches:false,addEventListener(){},removeEventListener(){}}))
 api.request.mockImplementation(async(path:string)=>{
  if(path==='/blog/site')return blankSite()
  if(path==='/admin/status')return {features:{dynamic_blog:true}}
  if(path.endsWith('/neighbors'))return path.includes('/one/')?pending:{previous:null,next:null}
  const id=path.split('/').pop();return {id,title:'故事'+id,body:'安静的正文',type_name:'生活',display_date:'2026-10-20',sections:[],fields:[],values:{},media:[],cover:null,places:[],links:[]}
 })
 const router=createRouter({history:createMemoryHistory(),routes:[{path:'/posts/:id',component:BlogView}]})
 const root=document.createElement('div');document.body.append(root);const app=createApp({render:()=>h(RouterView)}).use(router)
 const flush=async()=>{await new Promise(r=>setTimeout(r,0));await nextTick()}
 try{
  await router.push('/posts/one');await router.isReady();app.mount(root);await flush();await flush()
  expect(root.querySelector('h1')?.textContent).toBe('故事one');expect(root.querySelector('.adjacent-posts')).toBeNull()
  await router.push('/posts/two');await flush();await flush();expect(root.querySelector('h1')?.textContent).toBe('故事two')
  resolve({previous:{id:'stale',title:'旧页面的邻居',display_date:'2026-10-20',cover:null},next:null});await flush()
  expect(root.textContent).not.toContain('旧页面的邻居');expect(root.querySelector('h1')?.textContent).toBe('故事two')
 }finally{app.unmount();root.remove();vi.unstubAllGlobals();vi.restoreAllMocks()}
})

it('preserves the pinned revision query when a full-page Admin preview jumps to a chapter',async()=>{
 vi.stubGlobal('matchMedia',()=>({matches:false,addEventListener(){},removeEventListener(){}}));vi.spyOn(window,'scrollTo').mockImplementation(()=>{})
 api.request.mockReset().mockImplementation(async(path:string)=>{
  if(path==='/blog/site')return blankSite()
  if(path==='/admin/status')return {features:{dynamic_blog:true}}
  return {id:'one',title:'指定修订预览',body:'## 章节一\n正文\n## 章节二\n正文',type_name:'生活',display_date:'2026-10-20',sections:[],fields:[],values:{},media:[],cover:null,places:[],links:[],preview_revision:7}
 })
 const router=createRouter({history:createMemoryHistory(),routes:[{path:'/preview/posts/:id',component:BlogView}]});const root=document.createElement('div');document.body.append(root);const app=createApp({render:()=>h(RouterView)}).use(router)
 const flush=async()=>{await new Promise(r=>setTimeout(r,0));await nextTick()}
 try{
  await router.push('/preview/posts/one?revision=7');await router.isReady();app.mount(root);await flush();await flush();root.querySelector<HTMLAnchorElement>('.reading-toc a[href="#lj-post-one-heading-1"]')!.click();await flush();await flush()
  expect(router.currentRoute.value.query.revision).toBe('7');expect(router.currentRoute.value.hash).toContain('lj-post-one-heading-1')
  expect(api.request.mock.calls.filter(([path])=>path.startsWith('/admin/blog/preview/')).every(([path])=>path.includes('expected_revision=7'))).toBe(true)
 }finally{app.unmount();root.remove();vi.unstubAllGlobals();vi.restoreAllMocks()}
})
