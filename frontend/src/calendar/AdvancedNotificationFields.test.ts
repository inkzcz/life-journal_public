// @vitest-environment jsdom
import {createApp,nextTick,reactive,type App} from 'vue'
import {afterEach,expect,it,vi} from 'vitest'
import Fields from './AdvancedNotificationFields.vue'
const api=vi.hoisted(()=>({request:vi.fn()}))
vi.mock('../api',()=>api)
let app:App,root:HTMLElement
const flush=async()=>{for(let i=0;i<5;i++){await Promise.resolve();await nextTick()}}
afterEach(()=>{app?.unmount();root?.remove();api.request.mockReset()})
it('hides header values/body by default and previews only through the internal admin endpoint',async()=>{
 const value=reactive({method:'POST',url_template:'https://example.invalid/',headers:[{name:'Authorization',value:'synthetic-private-value'}],body_format:'json',body_template:'{"appToken":"synthetic-private-value"}'})
 root=document.createElement('div');document.body.append(root);app=createApp(Fields,{value});app.mount(root);await flush()
 expect(root.querySelector('input[type=password]')).not.toBeNull()
 expect(root.querySelector('textarea')).toBeNull();expect(root.textContent).not.toContain('synthetic-private-value')
 const buttons=()=>Array.from(root.querySelectorAll('button'))
 buttons().find(b=>b.textContent==='查看 / 编辑请求体')!.click();await flush()
 expect((root.querySelector('textarea') as HTMLTextAreaElement).value).toBe(value.body_template)
 api.request.mockResolvedValue({method:'POST',body:'[REDACTED]',external_request_sent:false})
 buttons().find(b=>b.textContent==='预览请求（不发送）')!.click();await flush()
 expect(api.request).toHaveBeenCalledOnce();expect(api.request.mock.calls[0]![0]).toBe('/admin/calendar/notification/preview')
 expect(root.querySelector('pre')?.textContent).toContain('[REDACTED]')
})
