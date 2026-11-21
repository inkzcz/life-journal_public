// @vitest-environment jsdom
import {createApp,nextTick} from 'vue'
import {it,expect,vi} from 'vitest'
import MediaTrash from './MediaTrash.vue'
const api=vi.hoisted(()=>({request:vi.fn()}));vi.mock('../api',()=>api)
it('requires count confirmation and keeps interrupted operations explicitly recoverable',async()=>{
 api.request.mockImplementation(async(p:string)=>p.startsWith('/admin/archive/media-trash?')?{items:[{id:'synthetic',revision:2,purge_operation_id:'pending'}],total:1}:p.startsWith('/admin/archive/media-purge-operations')?[{id:'pending',media_id:'synthetic',state:'prepared'}]:{items:[{media_id:'synthetic',state:'blocked'}]})
 const confirm=vi.spyOn(window,'confirm').mockReturnValue(true),prompt=vi.spyOn(window,'prompt').mockReturnValue('wrong')
 const root=document.createElement('div'),app=createApp(MediaTrash);document.body.append(root);app.mount(root);await new Promise(r=>setTimeout(r,0));await nextTick()
 const button=(s:string)=>Array.from(root.querySelectorAll('button')).find(b=>b.textContent===s)!
 button('全选当前页').click();await nextTick();button('永久删除所选图片').click();await nextTick();expect(api.request.mock.calls.some(([p])=>p.endsWith('/actions'))).toBe(false)
 expect(root.textContent).toContain('取消未提交删除');expect(root.textContent).toContain('不会在启动时自动重放')
 app.unmount();root.remove();confirm.mockRestore();prompt.mockRestore()
})
