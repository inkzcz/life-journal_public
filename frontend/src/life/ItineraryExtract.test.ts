// @vitest-environment jsdom
import {createApp,nextTick} from 'vue'
import {it,expect,vi} from 'vitest'
import ItineraryExtract from './ItineraryExtract.vue'
import {emptyLife} from './types'
const api=vi.hoisted(()=>({request:vi.fn()}));vi.mock('../api',()=>api)
it('previews without writing then explicitly appends to the shared local draft',async()=>{
 const item={id:'generated',source_key:'a'.repeat(64),title:'午餐',day:'2026-10-20',kind:'food'};api.request.mockResolvedValue({items:[item],body_hash:'b'.repeat(64),revision:3,warnings:[]})
 const life=emptyLife();life.activities.push({id:'manual',day:'2026-10-20',time:null,title:'手工活动',description:'',place_id:null,media_ids:[]});vi.spyOn(window,'confirm').mockReturnValue(true)
 const root=document.createElement('div');document.body.append(root);const app=createApp(ItineraryExtract,{recordId:'record',revision:3,body:'正文',value:life,disabled:false});app.mount(root)
 const flush=async()=>{await new Promise(r=>setTimeout(r,0));await nextTick()},button=(s:string)=>Array.from(root.querySelectorAll('button')).find(b=>b.textContent===s)!
 button('提取并预览行程').click();await flush();expect(life.activities).toHaveLength(1);button('确认追加所选活动到草稿').click();await flush();expect(life.activities.map(a=>a.id)).toEqual(['manual','generated']);expect(root.textContent).toContain('请保存')
 expect(api.request.mock.calls.every(([p])=>p.includes('itinerary-'))).toBe(true);app.unmount();root.remove();vi.restoreAllMocks()
})

it('shows reconciliation changes and preserved manual rows, locks writes, and only reloads after confirmed success',async()=>{
 api.request.mockReset().mockResolvedValueOnce({revision:4,body_hash:'c'.repeat(64),changes:[{operation:'add',item:{id:'new',day:'2026-10-03',title:'新景点'}},{operation:'update',item:{id:'auto',day:'2026-10-03',title:'新说明'}}],preserved:[{id:'manual',day:'2026-10-03',title:'人工活动'}],conflicts:[{id:'manual',title:'人工活动',message:'保留人工版本'}],warnings:[]}).mockResolvedValueOnce({id:'record',revision:5})
 vi.spyOn(window,'confirm').mockReturnValue(true)
 const events:unknown[]=[];const root=document.createElement('div');document.body.append(root)
 const app=createApp(ItineraryExtract,{recordId:'record',revision:4,body:'正文',value:emptyLife(),disabled:false,onPending:(value:boolean)=>events.push(value),onSynchronized:(value:any)=>events.push(value)})
 app.mount(root)
 const flush=async()=>{await new Promise(r=>setTimeout(r,0));await nextTick()},button=(name:string)=>Array.from(root.querySelectorAll('button')).find(b=>b.textContent===name)!
 try{
  button('预览完整行程差异').click();await flush()
  expect(root.textContent).toContain('更新自动活动');expect(root.textContent).toContain('保留人工活动');expect(root.textContent).toContain('冲突（保留人工版本）')
  expect(api.request).toHaveBeenCalledTimes(1)
  button('确认同步以上差异').click();await flush()
  expect(events).toEqual([true,false,{id:'record',revision:5}])
  expect(JSON.parse(String(api.request.mock.calls[1]![1]!.body))).toEqual({expected_revision:4,body_hash:'c'.repeat(64)})
 }finally{app.unmount();root.remove();vi.restoreAllMocks()}
})
