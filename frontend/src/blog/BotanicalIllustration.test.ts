// @vitest-environment jsdom
import {createApp,h} from 'vue'
import {expect,it} from 'vitest'
import ThemeOrnament from './ThemeOrnament.vue'
it('renders original botanical paint servers with unique IDs and no interactive or remote content',()=>{
 const root=document.createElement('div');document.body.append(root)
 const app=createApp({render:()=>h('main',[h(ThemeOrnament,{placement:'sidebar'}),h(ThemeOrnament)])});app.mount(root)
 try{
  const wrappers=Array.from(root.querySelectorAll('.theme-ornament'))
  expect(wrappers).toHaveLength(2)
  for(const node of wrappers){expect(node.getAttribute('aria-hidden')).toBe('true');expect(node.hasAttribute('inert')).toBe(true)}
  expect(wrappers[0]!.getAttribute('data-placement')).toBe('sidebar')
  const ids=Array.from(root.querySelectorAll('[id]')).map(e=>e.id)
  expect(new Set(ids).size).toBe(ids.length)
  for(const use of Array.from(root.querySelectorAll('use'))){const target=use.getAttribute('href')!;expect(target.startsWith('#')).toBe(true);expect(ids).toContain(target.slice(1))}
  expect(root.querySelector('image,foreignObject,script,a,animate,filter')).toBeNull()
  expect(root.querySelectorAll('.botanical-celadon use').length).toBeGreaterThan(15)
  expect(root.querySelectorAll('.botanical-lilac use').length).toBeGreaterThan(20)
 }finally{app.unmount();root.remove()}
})
