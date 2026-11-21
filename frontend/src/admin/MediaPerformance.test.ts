// @vitest-environment jsdom
import {createApp,nextTick,type App} from 'vue'
import {it,expect,vi,afterEach} from 'vitest'
import PrivatePreview from './PrivatePreview.vue'
import PhotoGallery from '../life/PhotoGallery.vue'
import {mediaRequest} from './mediaRequests'
const api=vi.hoisted(()=>({request:vi.fn()}));vi.mock('../api',()=>api)
const flush=async()=>{await new Promise(r=>setTimeout(r,0));await nextTick()}
let app:App|undefined,root:HTMLDivElement|undefined
 afterEach(()=>{app?.unmount();app=undefined;root?.remove();vi.unstubAllGlobals();vi.restoreAllMocks()})
it('does not request an offscreen image until intersection and aborts/unloads it on unmount',async()=>{
 let intersect:IntersectionObserverCallback=()=>{};const disconnect=vi.fn()
 vi.stubGlobal('IntersectionObserver',class{constructor(cb:IntersectionObserverCallback){intersect=cb}observe=vi.fn();disconnect=disconnect})
 api.request.mockReset().mockResolvedValue(new Blob(['synthetic']))
 URL.createObjectURL=vi.fn(()=> 'blob:private');URL.revokeObjectURL=vi.fn()
 root=document.createElement('div');document.body.append(root);app=createApp(PrivatePreview,{id:'synthetic',alt:'测试',width:400,height:600});app.mount(root);await flush()
 expect(api.request).not.toHaveBeenCalled();expect(root.querySelector('span')?.style.aspectRatio).toBe('400/600')
 intersect([{isIntersecting:true}] as IntersectionObserverEntry[],{} as IntersectionObserver);await flush()
 expect(api.request).toHaveBeenCalledTimes(1);expect(root.querySelector('img')?.getAttribute('width')).toBe('400');expect(root.querySelector('img')?.style.aspectRatio).toBe('400/600')
 const signal=api.request.mock.calls[0][1].signal as AbortSignal;app.unmount();app=undefined
 expect(signal.aborted).toBe(true);expect(disconnect).toHaveBeenCalled();expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:private')
})
it('bounds active private downloads to four and cancels a queued download without sending it',async()=>{
 api.request.mockReset();const finish:Array<()=>void>=[];api.request.mockImplementation(()=>new Promise<Blob>(resolve=>finish.push(()=>resolve(new Blob()))))
 const controllers=Array.from({length:7},()=>new AbortController());const jobs=controllers.map((c,i)=>mediaRequest('/library-media/'+i+'/thumbnail',c.signal).catch(e=>e.name))
 expect(api.request).toHaveBeenCalledTimes(4);controllers[5]!.abort();expect(await jobs[5]).toBe('AbortError')
 for(let i=0;i<6;i++){finish[i]!();await flush()}
 await Promise.all(jobs);expect(api.request).toHaveBeenCalledTimes(6)
 expect(api.request.mock.calls.some(([path])=>path.includes('/5/'))).toBe(false)
})
it('uses a large authenticated preview only when explicitly requested',async()=>{
 api.request.mockReset().mockResolvedValue(new Blob());URL.createObjectURL=vi.fn(()=> 'blob:large');URL.revokeObjectURL=vi.fn()
 root=document.createElement('div');document.body.append(root);app=createApp(PrivatePreview,{id:'full',alt:'灯箱',variant:'preview',eager:true});app.mount(root);await flush()
 expect(api.request).toHaveBeenCalledWith('/library-media/full/preview',{signal:expect.any(AbortSignal)})
})

it('keeps a large narrative gallery sharp with the private1600px preview',async()=>{
 api.request.mockReset().mockResolvedValue(new Blob());URL.createObjectURL=vi.fn(()=> 'blob:narrative');URL.revokeObjectURL=vi.fn()
 root=document.createElement('div');document.body.append(root);app=createApp(PhotoGallery,{photos:[{id:'narrative',alt:'叙事照片',width:1600,height:1067}],layout:'large'});app.mount(root);await flush()
 expect(api.request).toHaveBeenCalledWith('/library-media/narrative/preview',{signal:expect.any(AbortSignal)})
})
