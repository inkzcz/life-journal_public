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
 expect(dom.querySelector('.entry-details')?.textContent).toContain('2026-11-22')
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
