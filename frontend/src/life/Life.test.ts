// @vitest-environment jsdom
import { createApp,nextTick,type App } from 'vue'
import { beforeEach,afterEach,it,expect,vi } from 'vitest'
import PlaceMap from './PlaceMap.vue'
import LifeEditor from './LifeEditor.vue'
import LifeFeed from './LifeFeed.vue'
import { emptyLife,lifePayload,groupedDays,projectPlaces,photoGroups } from './types'
const api=vi.hoisted(()=>({request:vi.fn()}));vi.mock('../api',()=>api)
let root:HTMLDivElement,app:App|undefined
const places=[{id:'a',name:'山间',latitude:'0',longitude:'179',city:'虚构城',notes:'<script>纯文本</script>'},{id:'b',name:'海边',latitude:'1',longitude:'-179'},{id:'c',name:'没有坐标',latitude:null,longitude:null}]
const flush=async()=>{await new Promise(r=>setTimeout(r,0));await nextTick()}
beforeEach(()=>{root=document.createElement('div');document.body.append(root);api.request.mockResolvedValue(new Blob());URL.createObjectURL=vi.fn(()=> 'blob:synthetic');URL.revokeObjectURL=vi.fn()})
afterEach(()=>{app?.unmount();app=undefined;root.remove();vi.restoreAllMocks()})
it('groups days chronologically and preserves custom order within each day',()=>{const a:any=[{id:'c',day:'2026-10-20'},{id:'b',day:'2026-10-18'},{id:'a',day:'2026-10-18'}];expect(groupedDays(a).map(g=>[g.day,g.items.map(a=>a.id)])).toEqual([['2026-10-18',['b','a']],['2026-10-20',['c']]])})
it('projects zero coordinates and antimeridian places without network APIs',()=>{const points=projectPlaces(places);expect(points).toHaveLength(2);expect(points.every(p=>p.x>=60&&p.x<=740&&p.y>=60&&p.y<=340)).toBe(true);expect(projectPlaces([{latitude:'0',longitude:'0'}])[0]).toMatchObject({x:400,y:200});expect(projectPlaces([{latitude:'NaN',longitude:'2'}])).toEqual([])})
it('always retains the coordinate-free place list when the map is unavailable',async()=>{app=createApp(PlaceMap,{article:{places,media:[],life:emptyLife()},available:false});app.mount(root);await flush();expect(root.querySelector('svg')).toBeNull();expect(root.textContent).toContain('没有坐标');expect(root.textContent).toContain('地点列表始终可读');expect(api.request).not.toHaveBeenCalled();expect(root.querySelector('script')).toBeNull()})
it('emits selected map and list places to synchronize itinerary highlights',async()=>{const select=vi.fn();app=createApp(PlaceMap,{article:{places,media:[],life:emptyLife()},selected:'a',onSelect:select});app.mount(root);await flush();root.querySelector<SVGGElement>('[aria-label="地图地点：海边"]')!.dispatchEvent(new MouseEvent('click',{bubbles:true}));expect(select).toHaveBeenCalledWith('b');expect(root.querySelector('.map-place-list [aria-pressed=true]')?.textContent).toContain('山间')})
it('groups photos by date/place/manual without duplicating or reordering within groups',()=>{const photos=[{id:'1'},{id:'2'},{id:'3'}],notes=[{media_id:'1',taken_on:'2026-10-20',place_id:'a',group_name:'旅途'},{media_id:'2',taken_on:'2026-10-18',place_id:'a',group_name:'旅途'}];expect(photoGroups(photos,notes,places,'date').map(g=>g.name)).toEqual(['2026-10-18','2026-10-20','日期未指定']);expect(photoGroups(photos,notes,places,'place')[0]?.photos.map(p=>p.id)).toEqual(['1','2']);expect(photoGroups(photos,notes,places,'manual')[0]?.name).toBe('旅途')})
it('stages itinerary edits locally and normalizes blank optional times',async()=>{const life=emptyLife();app=createApp(LifeEditor,{travel:true,value:life,connections:{media:[],places:[],links:[],incoming:[]},disabled:false});app.mount(root);await flush();Array.from(root.querySelectorAll('button')).find(b=>b.textContent==='添加行程活动')!.click();await nextTick();expect(life.activities).toHaveLength(1);life.activities[0]!.time='';expect(lifePayload(life).activities[0]?.time).toBeNull();expect(api.request).not.toHaveBeenCalled()})
it('builds private timeline/year filters and links using supplied records',async()=>{const navigate=vi.fn();app=createApp(LifeFeed,{data:{years:[2025],types:[{id:'t',name:'自定义类型'}],items:[{id:'r',title:'虚构记录',display_date:'2025-01-01',type_name:'类型',excerpt:''}],total:1},annual:false,year:'2025',typeId:'t',page:1,onNavigate:navigate});app.mount(root);await flush();root.querySelector('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));expect(navigate).toHaveBeenCalledWith('/timeline?page=1&type_id=t&year=2025');expect(root.querySelector('a[href="/posts/r"]')?.textContent).toContain('虚构记录')})
it('copies chosen existing date fields only after explicit confirmation',async()=>{
 const life=emptyLife(),fields=[{id:'start',name:'自定义启程日期',value:'2026-10-20'},{id:'end',name:'自定义归来日期',value:'2026-10-23'}];vi.spyOn(window,'confirm').mockReturnValue(true)
 app=createApp(LifeEditor,{travel:true,value:life,connections:{media:[],places:[],links:[],incoming:[]},disabled:false,dateFields:fields});app.mount(root);await flush();expect(life.start_date).toBeNull()
 const select=(name:string,value:string)=>{const input=Array.from(root.querySelectorAll('label')).find(l=>l.textContent?.startsWith(name))!.querySelector('select')!;input.value=value;input.dispatchEvent(new Event('change',{bubbles:true}))}
 select('开始日期来源','start');select('结束日期来源','end');await nextTick();Array.from(root.querySelectorAll('button')).find(b=>b.textContent==='采用所选日期')!.click();await nextTick();expect(life.start_date).toBe('2026-10-20');expect(life.end_date).toBe('2026-10-23');expect(fields[0]!.value).toBe('2026-10-20')
})

it('hides itinerary editing in ordinary mode without deleting retained activities',async()=>{
 const life=emptyLife();life.activities=[{id:'retained',day:'2026-11-13',title:'保留行程',media_ids:[]} as any]
 app=createApp(LifeEditor,{travel:false,value:life,connections:{media:[],places:[],links:[],incoming:[]},disabled:false});app.mount(root);await flush()
 expect(root.textContent).not.toContain('添加行程活动');expect(life.activities.map(a=>a.id)).toEqual(['retained'])
})
