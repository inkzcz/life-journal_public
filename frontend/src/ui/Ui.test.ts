// @vitest-environment jsdom
import { createApp,nextTick,h,reactive,type App } from 'vue'
import { it,expect,vi,afterEach } from 'vitest'
import PrivatePreview from '../admin/PrivatePreview.vue'
import PhotoGallery from '../life/PhotoGallery.vue'
const api=vi.hoisted(()=>({request:vi.fn()}));vi.mock('../api',()=>api)
let app:App|undefined,root:HTMLDivElement
const flush=async()=>{await new Promise(r=>setTimeout(r,0));await nextTick()}
afterEach(()=>{app?.unmount();root?.remove();vi.restoreAllMocks();vi.unstubAllGlobals()})
it('removes a failed decoded private image and revokes its URL without leaving a broken image',async()=>{
 api.request.mockResolvedValue(new Blob(['invalid image']));URL.createObjectURL=vi.fn(()=> 'blob:synthetic');URL.revokeObjectURL=vi.fn()
 root=document.createElement('div');document.body.append(root);app=createApp(PrivatePreview,{id:'private',alt:'合成图片'});app.mount(root);await flush()
 root.querySelector('img')!.dispatchEvent(new Event('error'));await nextTick()
 expect(root.querySelector('img')).toBeNull();expect(root.textContent).toContain('图片暂不可用');expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:synthetic')
})
it('keeps supplied photo order across masonry updates and does not mutate the record array',async()=>{
 api.request.mockResolvedValue(new Blob());URL.createObjectURL=vi.fn(()=> 'blob:synthetic');URL.revokeObjectURL=vi.fn()
 const photos=[{id:'b',alt:'第二个标识在前'},{id:'a',alt:'第一个标识在后'}]
 root=document.createElement('div');document.body.append(root);app=createApp(PhotoGallery,{photos,layout:'masonry'});app.mount(root);await flush()
 expect(Array.from(root.querySelectorAll('.photo-button')).map(e=>e.getAttribute('aria-label'))).toEqual(['放大图片：第二个标识在前','放大图片：第一个标识在后'])
 expect(photos.map(p=>p.id)).toEqual(['b','a'])
})

it('clears masonry row spans when the template preview changes back to grid',async()=>{
 vi.stubGlobal('ResizeObserver',class {observe(){} disconnect(){}})
 api.request.mockResolvedValue(new Blob());URL.createObjectURL=vi.fn(()=> 'blob:synthetic');URL.revokeObjectURL=vi.fn()
 const state=reactive({layout:'masonry'})
 root=document.createElement('div');document.body.append(root)
 app=createApp({setup:()=>()=>h(PhotoGallery,{photos:[{id:'a',alt:'示例'}],layout:state.layout})});app.mount(root);await flush()
 expect(root.querySelector<HTMLElement>('figure')!.style.gridRowEnd).toContain('span')
 state.layout='grid';await flush()
 expect(root.querySelector<HTMLElement>('figure')!.style.gridRowEnd).toBe('')
})
