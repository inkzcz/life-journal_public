// @vitest-environment jsdom
import {createApp,h,nextTick} from 'vue'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import ThemeBoundary from './ThemeBoundary.vue'
import ReaderShell from '../blog/ReaderShell.vue'
import {activeAppearance,savedAppearance,rememberAppearance,previewAppearance,cancelAppearancePreview,sanitizeAppearance,installAppearance,refreshAppearance,APPEARANCE_CACHE} from './theme'
const api=vi.hoisted(()=>({request:vi.fn()}));vi.mock('../api',()=>api)
let dispose:(()=>void)|undefined
const owner=Symbol('unit-preview')
beforeEach(()=>{localStorage.clear();rememberAppearance({theme:'celadon',style:'modern-soft',palette:'celadon',mode:'light'});api.request.mockReset()})
afterEach(()=>{dispose?.();dispose=undefined;cancelAppearancePreview(owner);document.documentElement.removeAttribute('style');vi.restoreAllMocks()})
it('whitelists cache keys and colors without keeping private content or executable styles',()=>{
 const a=sanitizeAppearance({theme:'glass',style:'editorial',palette:'lilac',mode:'dark',body:'private',token:'secret',colors:{glass:{light:{accent:'#123456',link:'url(javascript:bad)',unknown:'#ffffff'}}},combination_colors:{editorial:{lilac:{dark:{}}},evil:{celadon:{light:{accent:'#111111'}}}}})
 expect(a).toEqual({theme:'glass',style:'editorial',palette:'lilac',mode:'dark',colors:{glass:{light:{accent:'#123456'}}},combination_colors:{editorial:{lilac:{dark:{}}}}})
 rememberAppearance(a);expect(localStorage.getItem(APPEARANCE_CACHE)).not.toContain('private');expect(localStorage.getItem(APPEARANCE_CACHE)).not.toContain('secret')
})
it('keeps preview/cancel separate from persistence and ignores another owner cancellation',()=>{
 const cached=localStorage.getItem(APPEARANCE_CACHE)
 previewAppearance(owner,{theme:'soft',style:'glass',palette:'lilac',mode:'dark'});expect(activeAppearance.value.palette).toBe('lilac');expect(savedAppearance.value.palette).toBe('celadon');expect(localStorage.getItem(APPEARANCE_CACHE)).toBe(cached)
 cancelAppearancePreview(Symbol('other'));expect(activeAppearance.value.palette).toBe('lilac');cancelAppearancePreview(owner);expect(activeAppearance.value.palette).toBe('celadon')
})
it('one OS listener drives system mode while manual mode wins for root and Teleport inheritance',async()=>{
 let changed=()=>{};const mq={matches:true,addEventListener:vi.fn((_,cb)=>{changed=cb}),removeEventListener:vi.fn()};vi.stubGlobal('matchMedia',()=>mq)
 dispose=installAppearance();expect(document.documentElement.dataset.mode).toBe('light')
 rememberAppearance({theme:'modern',mode:'system'});expect(document.documentElement.dataset.mode).toBe('dark');mq.matches=false;changed();expect(document.documentElement.dataset.mode).toBe('light')
 rememberAppearance({theme:'modern',mode:'dark',colors:{modern:{dark:{accent:'#aabbcc'}}}});mq.matches=false;changed();expect(document.documentElement.dataset.mode).toBe('dark');expect(document.documentElement.style.getPropertyValue('--reader-accent')).toBe('#aabbcc')
 expect(mq.addEventListener).toHaveBeenCalledTimes(1);vi.unstubAllGlobals()
})
it('does not allow an older in-flight refresh to replace a successful save',async()=>{
 let resolve!:(value:any)=>void;api.request.mockReturnValue(new Promise(r=>resolve=r));const pending=refreshAppearance()
 rememberAppearance({theme:'soft',style:'editorial',palette:'lilac',mode:'dark'});resolve({appearance:{theme:'modern',mode:'light'}});await pending;expect(savedAppearance.value.palette).toBe('lilac')
})
it('renders real independent boundaries without copying private data or changing saved state',async()=>{
 const root=document.createElement('div');document.body.append(root)
 const app=createApp({render:()=>h(ThemeBoundary,{appearance:{theme:'modern',style:'modern-flat',palette:'lilac',mode:'dark',combination_colors:{'modern-flat':{lilac:{dark:{heading_text:'#abcdef'}}}}}},()=>h('button','真实按钮'))});app.mount(root);await nextTick()
 expect(root.firstElementChild?.getAttribute('data-style')).toBe('modern-flat');expect(root.firstElementChild?.getAttribute('data-palette')).toBe('lilac');expect((root.firstElementChild as HTMLElement).style.getPropertyValue('--reader-heading-text')).toBe('#abcdef');expect(savedAppearance.value.palette).toBe('celadon');app.unmount();root.remove()
})

it('ignores a private metadata response after its reading shell is unmounted',async()=>{
 let resolve!:(value:any)=>void;api.request.mockReturnValue(new Promise(r=>resolve=r));const root=document.createElement('div');document.body.append(root);const app=createApp(ReaderShell);app.component('RouterLink',{template:'<a><slot/></a>'});app.mount(root);app.unmount();rememberAppearance({theme:'soft',style:'editorial',palette:'lilac',mode:'dark'});resolve({title:'late response',appearance:{theme:'modern',mode:'light'}});await Promise.resolve();await nextTick();expect(savedAppearance.value.palette).toBe('lilac');root.remove()
})

it('keeps a newer cross-tab appearance when an older refresh finishes',async()=>{
 dispose=installAppearance();let resolve!:(value:any)=>void;api.request.mockReturnValue(new Promise(r=>resolve=r));const pending=refreshAppearance();window.dispatchEvent(new StorageEvent('storage',{key:APPEARANCE_CACHE,newValue:JSON.stringify({theme:'soft',style:'editorial',palette:'lilac',mode:'dark'})}));resolve({appearance:{theme:'modern',mode:'light'}});await pending;expect(savedAppearance.value.palette).toBe('lilac')
})

it('does not let a mounted reading shell overwrite a newer appearance while metadata is in flight',async()=>{
 let resolve!:(value:any)=>void;api.request.mockReturnValue(new Promise(r=>resolve=r));const root=document.createElement('div');document.body.append(root);const app=createApp(ReaderShell);app.component('RouterLink',{template:'<a><slot/></a>'});app.mount(root);rememberAppearance({theme:'soft',style:'editorial',palette:'lilac',mode:'dark'});resolve({title:'late metadata',appearance:{theme:'modern',mode:'light'}});await Promise.resolve();await nextTick();expect(savedAppearance.value.palette).toBe('lilac');app.unmount();root.remove()
})
