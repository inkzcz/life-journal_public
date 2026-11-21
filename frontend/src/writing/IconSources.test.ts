// @vitest-environment jsdom
import {createApp,h} from 'vue'
import {expect,it} from 'vitest'
import ModuleIcon from './ModuleIcon.vue'
import {moduleIconPaths,placeIconPaths} from './iconPaths'
import {renderMarkdown} from '../markdown'

it.each(['basic','body','media','itinerary','relations','publish','unrecognized'])('retains the local accessible module icon for %s',kind=>{
 const root=document.createElement('div'),app=createApp({render:()=>h(ModuleIcon,{kind})});document.body.append(root);app.mount(root)
 try{
  expect(root.querySelector('.module-icon')?.getAttribute('aria-hidden')).toBe('true')
  expect(root.querySelector('svg')?.getAttribute('viewBox')).toBe('0 0 24 24')
  expect(root.querySelector('path')?.getAttribute('d')).toBe(moduleIconPaths[kind]||moduleIconPaths.body)
  expect(root.querySelector('image,use,script,a')).toBeNull()
 }finally{app.unmount();root.remove()}
})

it.each(['l','f','s','h','t','c','p'])('keeps the %s place label and local geometry without adding remote content',kind=>{
 const template=document.createElement('template');template.innerHTML=renderMarkdown(`@${kind}[合成地点]`)
 const marker=template.content.querySelector('.lj-place-mark')!
 expect(marker.getAttribute('data-mark-kind')).toBe(kind)
 expect(marker.textContent).toBe('合成地点')
 expect(marker.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true')
 expect(marker.querySelector('path')?.getAttribute('d')).toBe(placeIconPaths[kind])
 expect(marker.querySelector('image,use,script,a')).toBeNull()
})
