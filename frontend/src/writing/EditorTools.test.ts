// @vitest-environment jsdom
import {createApp,h,nextTick,ref} from 'vue'
import {it,expect,vi} from 'vitest'
import EditorTools from './EditorTools.vue'
it('locks only mobile scrolling, handles Escape, restores focus and cleans up on unmount',async()=>{
 const original=document.body.style.overflow;document.body.style.overflow='auto'
 const media={matches:true,addEventListener:vi.fn(),removeEventListener:vi.fn()};vi.stubGlobal('matchMedia',()=>media)
 const root=document.createElement('div'),launch=document.createElement('button');document.body.append(launch,root);launch.focus()
 const open=ref(false);const app=createApp({render:()=>h(EditorTools,{open:open.value,active:'media',hasAI:true,top:88,onClose:()=>open.value=false},{media:()=>h('input')})});app.mount(root)
 try{open.value=true;await nextTick();await nextTick();expect(document.body.style.overflow).toBe('hidden');expect(root.querySelector('aside')?.getAttribute('role')).toBe('dialog');root.querySelector('aside')!.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));await nextTick();await nextTick();expect(open.value).toBe(false);expect(document.body.style.overflow).toBe('auto');expect(document.activeElement).toBe(launch);open.value=true;await nextTick();app.unmount();expect(document.body.style.overflow).toBe('auto')}finally{app.unmount();root.remove();launch.remove();document.body.style.overflow=original;vi.unstubAllGlobals()}
})
