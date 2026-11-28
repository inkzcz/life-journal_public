// @vitest-environment jsdom
import {createApp,h,nextTick,reactive,type App} from 'vue'
import {afterEach,expect,it} from 'vitest'
import TransportTimeFields from './TransportTimeFields.vue'
import {blankEntry} from './entries'
let app:App,root:HTMLElement
function mount(fields:Record<string,string>={},siteZone='Asia/Shanghai',recordDate?:string){
 const value=reactive(blankEntry('t'));value.fields=fields
 const validity:boolean[]=[];root=document.createElement('div');document.body.append(root)
 app=createApp({render:()=>h(TransportTimeFields,{value,siteZone,recordDate,onValidity:(v:boolean)=>validity.push(v)})});app.mount(root)
 return {value,validity}
}
afterEach(()=>{app?.unmount();root?.remove()})
async function change(label:string,value:string){const input=root.querySelector(`[aria-label="${label}"]`) as HTMLInputElement;input.value=value;input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));await nextTick()}
it('preserves historical offset, seconds and unparseable values merely opened',()=>{
 const fields={departure_at:'2026-07-15T12:00:30.123-05:00',departure_zone:'America/New_York',arrival_at:'old unknown text'}
 const before=JSON.stringify(fields),{value}=mount(fields);expect(JSON.stringify(value.fields)).toBe(before);expect(root.textContent).toContain('原值保持');expect(root.textContent).toContain('无法自动解析')
})
it('uses site timezone for new entries and computes duration only after explicit inputs',async()=>{
 const {value,validity}=mount();expect(value.fields).toEqual({})
 await change('出发日期','2026-11-13');expect(validity.at(-1)).toBe(false)
 await change('出发时间','15:43');await change('到达日期','2026-11-13');await change('到达时间','17:36')
 expect(value.fields.departure_at).toBe('2026-11-13T15:43+08:00');expect(value.fields.arrival_zone).toBe('Asia/Shanghai');expect(root.textContent).toContain('1小时53分钟');expect(validity.at(-1)).toBe(true)
})
it('blocks nonexistent times, requires explicit overlap choice, then commits selected offset',async()=>{
 const {value,validity}=mount({},'America/New_York');await change('出发日期','2026-03-08');await change('出发时间','02:30')
 expect(root.textContent).toContain('不存在');expect(value.fields.departure_at).toBeUndefined();expect(validity.at(-1)).toBe(false)
 await change('出发日期','2026-11-01');const lastValid=value.fields.departure_at;await change('出发时间','01:30');expect(root.textContent).toContain('当地时间重复');expect(value.fields.departure_at).toBe(lastValid);expect(validity.at(-1)).toBe(false)
 const select=root.querySelector('select')!;select.value=select.options[2]!.value;select.dispatchEvent(new Event('change',{bubbles:true}));await nextTick()
 expect(value.fields.departure_at).toBe('2026-11-01T01:30-05:00');expect(validity.at(-1)).toBe(true)
})
it('does not guess browser timezone when site setting unavailable; accepts explicit IANA zone',async()=>{
 const {value}=mount({},'');await change('出发日期','2026-11-13');await change('出发时间','12:00');expect(value.fields.departure_at).toBeUndefined();expect(root.textContent).toContain('不会使用浏览器时区')
 const toggle=root.querySelector('[aria-label=独立时区]') as HTMLInputElement;toggle.checked=true;toggle.dispatchEvent(new Event('change',{bubbles:true}));await nextTick();await change('时区切换方式','local');(Array.from(root.querySelectorAll('button')).find(b=>b.textContent==='应用时区切换') as HTMLButtonElement).click();await nextTick();await change('出发地时区','Asia/Kathmandu');expect(value.fields.departure_at).toBe('2026-11-13T12:00+05:45')
})
it('rejects actual negative journey but accepts earlier local arrival across zones',async()=>{
 const {value,validity}=mount({departure_at:'2026-11-13T18:00+09:00',departure_zone:'Asia/Tokyo',arrival_at:'2026-11-13T11:00-08:00',arrival_zone:'America/Los_Angeles'})
 expect(root.textContent).toContain('10小时');await change('到达地时区','Asia/Tokyo');expect(value.fields.arrival_at).toBe('2026-11-13T11:00+09:00');expect(validity.at(-1)).toBe(false);expect(root.textContent).toContain('早于出发')
})

it('starts with site zone, defaults to the article date and follows until arrival date is explicitly changed',async()=>{
 const {value}=mount({},'Asia/Shanghai','2026-12-31')
 expect(root.querySelector('[aria-label="出发地时区"]')).toBeNull()
 expect((root.querySelector('[aria-label="出发日期"]') as HTMLInputElement).value).toBe('2026-12-31')
 expect(value.fields).toEqual({})
 await change('出发时间','23:30');await change('到达时间','23:50');await change('出发日期','2027-01-01')
 expect(value.fields.arrival_at).toBe('2027-01-01T23:50+08:00')
 await change('到达日期','2027-01-03');await change('出发日期','2027-01-02')
 expect(value.fields.arrival_at).toBe('2027-01-03T23:50+08:00');expect(value.fields.independent_zones).toBe('false')
})
it.each(['instant','local'])('requires an explicit %s policy when disabling historical independent zones',async policy=>{
 const {value,validity}=mount({departure_at:'2026-11-13T10:00:30.123+09:00',arrival_at:'2026-11-13T12:00+09:00',departure_zone:'Asia/Tokyo',arrival_zone:'Asia/Tokyo'})
 const before=JSON.stringify(value.fields),toggle=root.querySelector('[aria-label="独立时区"]') as HTMLInputElement
 toggle.checked=false;toggle.dispatchEvent(new Event('change',{bubbles:true}));await nextTick()
 expect(JSON.stringify(value.fields)).toBe(before);expect(validity.at(-1)).toBe(false)
 await change('时区切换方式',policy);(Array.from(root.querySelectorAll('button')).find(b=>b.textContent==='应用时区切换') as HTMLButtonElement).click();await nextTick()
 expect(value.fields.departure_at).toBe(policy==='instant'?'2026-11-13T09:00:30.123+08:00':'2026-11-13T10:00:30.123+08:00')
 expect(value.fields.independent_zones).toBe('false');expect(root.querySelector('[aria-label="出发地时区"]')).toBeNull()
})

it('uses the current site zone for edits in explicit site mode without rewriting a historical stamp on mount',async()=>{
 const {value}=mount({independent_zones:'false',departure_zone:'Asia/Shanghai',departure_at:'2026-11-13T10:00+08:00'},'Asia/Tokyo')
 expect(value.fields.departure_at).toBe('2026-11-13T10:00+08:00');expect(root.querySelector('[aria-label="出发地时区"]')).toBeNull()
 await change('出发时间','11:00');expect(value.fields.departure_at).toBe('2026-11-13T11:00+09:00')
})
