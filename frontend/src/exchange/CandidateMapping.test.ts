// @vitest-environment jsdom
import {createApp,h,reactive,nextTick,type App} from 'vue'
import {it,expect,vi,afterEach} from 'vitest'
import RecordMapping from './RecordMapping.vue'
import ResourceMapping from './ResourceMapping.vue'
const api=vi.hoisted(()=>({request:vi.fn()}));vi.mock('../api',()=>api)
let app:App,root:HTMLElement
async function click(text:string){Array.from(root.querySelectorAll('button')).find(b=>b.textContent===text)!.click();await nextTick()}
afterEach(()=>{app?.unmount();root?.remove();vi.clearAllMocks()})
it('fills missing candidate travel/food without guessing dates or saving global entities',async()=>{
 const record=reactive<any>({tags:[],media_keys:[],cover_key:null,travel:null,foods:[],photos:[],links:[]}),content=reactive<any>({media:[],places:[{key:'meal',name:'合成餐厅',kind:'f'}],records:[record]});const change=vi.fn()
 root=document.createElement('div');document.body.append(root);app=createApp({render:()=>h(RecordMapping,{record,content,onChange:change})});app.mount(root)
 await click('补充旅行安排（可选）');expect(record.travel).toEqual({start_date:null,end_date:null,activities:[]})
 await click('添加候选活动');expect(record.travel.activities[0]).toMatchObject({day:'',time:null,place_key:null,media_keys:[]});expect(record.travel.activities[0].key).toMatch(/^activity_[a-f0-9-]{36}$/)
 await click('补充餐饮候选');expect(record.foods).toEqual([{place_key:'',day:null,time:null,review:'',media_keys:[]}])
 await click('仅移除此候选活动');await click('仅移除此餐饮候选');expect(record.travel.activities).toEqual([]);expect(record.foods).toEqual([]);expect(change).toHaveBeenCalled();expect(api.request).not.toHaveBeenCalled()
})
it('lets an empty extra place candidate be removed and blocks removal while a candidate activity uses it',async()=>{
 const content=reactive<any>({records:[{body:'原正文',travel:{activities:[]},foods:[],photos:[]}],places:[],media:[]});root=document.createElement('div');document.body.append(root);app=createApp({render:()=>h(ResourceMapping,{content})});app.mount(root)
 await click('补充地点候选（确认前不创建）');const place=content.places[0];expect(place).toMatchObject({name:'',city:'',existing_id:null})
 content.records[0].travel.activities.push({place_key:place.key});await nextTick();await click('仅移除此地点候选（地点库不变）');expect(content.places).toHaveLength(1);expect(root.textContent).toContain('仍被候选正文')
 content.records[0].travel.activities=[];await click('仅移除此地点候选（地点库不变）');expect(content.places).toEqual([]);expect(api.request).not.toHaveBeenCalled()
})
