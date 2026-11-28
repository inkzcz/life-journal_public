// @vitest-environment jsdom
import {createApp,h,type App} from 'vue'
import {afterEach,expect,it} from 'vitest'
import EntryCard from './EntryCard.vue'
import {entryNames,type Entry,type EntryKind,serializeEntry,readEntry} from './entries'

let app:App|undefined,root:HTMLElement|undefined
function mount(entry:Entry,media=false){
 root=document.createElement('div');document.body.append(root)
 app=createApp({render:()=>h(EntryCard,{entry},media?{media:()=>h('img',{alt:'合成关联照片','data-media-id':entry.media_ids[0]})}:undefined)})
 app.mount(root);return root
}
afterEach(()=>{app?.unmount();root?.remove()})
const entry=(kind:EntryKind):Entry=>({id:'11111111-1111-4111-8111-111111111111',kind,name:'合成生活片段',fields:{},media_ids:[]})

it.each(Object.keys(entryNames) as EntryKind[])('renders %s using one card without inventing empty fields or photos',kind=>{
 const value=entry(kind),before=serializeEntry(value),dom=mount(value,true)
 expect(dom.querySelector('.entry-kicker')?.textContent).toContain(entryNames[kind])
 expect(dom.querySelector('.entry-title')?.textContent).toBe(value.name)
 expect(dom.querySelector('dl')).toBeNull();expect(dom.querySelector('.entry-visuals')).toBeNull()
 expect(dom.querySelector('img')).toBeNull();expect(serializeEntry(value)).toBe(before)
})

it('retains dated details, multiline reflections, known historical fields and source identities',()=>{
 const value=entry('m');value.fields={date:'2026-11-22',time:'19:30',cinema:'合成影院'.repeat(30),review:'第一行\n第二行',seat:'',person:'合成同行人'}
 value.media_ids=['22222222-2222-4222-8222-222222222222']
 const before=serializeEntry(value),dom=mount(value,true)
 expect(dom.querySelector('.movie-information')?.textContent).toContain('2026-11-22')
 expect(dom.querySelector('.entry-details')?.textContent).toContain('合成同行人')
 expect(dom.querySelector('.entry-reflection p')?.textContent).toBe('第一行\n第二行')
 expect(dom.textContent).not.toContain('座位')
 expect(dom.querySelector('img')?.getAttribute('data-media-id')).toBe(value.media_ids[0])
 expect(readEntry(before+'\n')?.attrs).toEqual(value);expect(serializeEntry(value)).toBe(before)
})

it('shows source-authored place notes without exposing internal UUIDs or executing HTML',()=>{
 const value=entry('l');value.name='<img src=x onerror=alert(1)>'
 value.fields={description:'<script>synthetic()</script>',place_id:'33333333-3333-4333-8333-333333333333',date:'2026-11-22'}
 const dom=mount(value)
 expect(dom.textContent).toContain(value.name);expect(dom.textContent).toContain(value.fields.description)
 expect(dom.textContent).toContain('2026-11-22');expect(dom.textContent).not.toContain(value.fields.place_id)
 expect(dom.querySelector('script,img')).toBeNull()
})

it('renders G8533 as two endpoints and an actual duration without inventing arrival station',()=>{const value=entry('t');value.name='G8533';value.fields={transport_type:'高铁',departure:'重庆',destination:'成都',departure_station:'沙坪坝',departure_at:'2026-11-13T15:43+08:00',arrival_at:'2026-11-13T17:36+08:00'};const dom=mount(value);expect(dom.querySelector('.route-start')?.textContent).toContain('15:43重庆沙坪坝');expect(dom.querySelector('.route-end')?.textContent).toBe('17:36成都');expect(dom.querySelector('.route-duration')?.textContent).toBe('1小时53分钟');expect(dom.querySelector('.route-end p')).toBeNull();expect(dom.querySelector('.entry-details')).toBeNull()})
it('uses six distinct content structures and preserves unknown legal historical fields',()=>{const value=entry('f');value.fields={rating:'4.5',price_per_person:'98',custom_memory:'合成未知扩展'};const dom=mount(value);expect(dom.querySelector('.food-meal.no-media')).not.toBeNull();expect(dom.querySelector('.card-rating')?.textContent).toBe('4.5');expect(dom.textContent).not.toContain('/ 5');expect(dom.textContent).not.toContain('¥');expect(dom.querySelector('.entry-extra')?.textContent).toContain('合成未知扩展')})

it('keeps crossing dates explicit and timezone data private while using absolute DST duration',()=>{
 const value=entry('t');value.fields={transport_type:'飞机',departure:'合成出发地'.repeat(30),destination:'合成目的地'.repeat(30),departure_at:'2026-11-01T01:30-04:00',arrival_at:'2026-11-01T02:30-05:00',departure_zone:'America/New_York',arrival_zone:'America/New_York',description:'合成备注\n'.repeat(40)}
 const before=serializeEntry(value),dom=mount(value)
 expect(dom.textContent).not.toContain('America/New_York');expect(dom.querySelector('.route-duration')?.textContent).toBe('2小时');expect(dom.querySelectorAll('.transport-meta time')).toHaveLength(1)
 expect(dom.querySelector('.entry-reflection p')?.textContent).toBe(value.fields.description);expect(dom.querySelector('.ticket-perforation')).toBeNull();expect(serializeEntry(value)).toBe(before)
})
it('shows both dates across a year boundary and only active transport fields',()=>{
 const value=entry('t');value.fields={transport_type:'自驾',departure_at:'2026-12-31T23:00+08:00',arrival_at:'2027-01-01T01:00+08:00',distance:'120 km',carriage:'05',seat:'08A',airline:'合成航空'}
 const dom=mount(value)
 expect(dom.querySelector('.route-start .route-date')?.textContent).toBe('2026-12-31');expect(dom.querySelector('.route-end .route-date')?.textContent).toBe('2027-01-01')
 expect(dom.textContent).toContain('120 km');expect(dom.textContent).not.toContain('08A');expect(dom.textContent).not.toContain('合成航空')
})
it.each(['f','m'] as const)('preserves a custom rating scale on %s instead of converting it',kind=>{
 const value=entry(kind);value.fields={rating:'87',rating_scale:'百分制'}
 const dom=mount(value);expect(dom.querySelector('.card-rating')?.textContent).toBe('87 / 百分制')
})
