// @vitest-environment jsdom
import { createApp,nextTick,type App } from 'vue'
import { createRouter,createMemoryHistory } from 'vue-router'
import { beforeEach,afterEach,it,expect,vi } from 'vitest'
import TrashAdmin from './TrashAdmin.vue'
import HistoryView from './HistoryView.vue'
import MaintenanceAdmin from './MaintenanceAdmin.vue'
const api=vi.hoisted(()=>({request:vi.fn()}));vi.mock('../api',()=>api)
let app:App,root:HTMLDivElement
const record={id:'r1',type_id:'t1',type_name:'自定义生活',title:'虚构故事',body:'## 安全正文',display_date:'2026-10-19',status:'published',schema_version:1,revision:2,fields:[],values:{},deleted_at:'2026-10-19T00:00:00Z',created_at:'2026-10-18T00:00:00Z',connections:{media:[],places:[],links:[]}}
const flush=async()=>{await new Promise(r=>setTimeout(r,0));await nextTick()}
function button(name:string){const el=Array.from(root.querySelectorAll('button')).find(e=>e.textContent?.trim()===name);if(!el)throw Error(name);return el}
async function mount(component:any,path='/admin/trash'){const router=createRouter({history:createMemoryHistory(),routes:[{path:'/admin/history/:id',component:{template:'<div />'}},{path:'/:all(.*)*',component:{template:'<div />'}}]});await router.push(path);await router.isReady();app=createApp(component);app.use(router);app.mount(root);await flush();await flush()}
beforeEach(()=>{root=document.createElement('div');document.body.append(root);vi.spyOn(window,'confirm').mockReturnValue(true);vi.spyOn(window,'prompt').mockReturnValue('永久删除');api.request.mockReset().mockImplementation(async(path:string,options?:RequestInit)=>{
 if(path==='/admin/content/types')return [{id:'t1',name:'自定义生活'}]
 if(path.startsWith('/admin/recovery/trash?'))return {items:[structuredClone(record)],total:1}
 if(path==='/admin/recovery/media')return []
 if(path==='/admin/recovery/trash/r1')return {...structuredClone(record),warnings:['导航仍引用此记录']}
 if(path.startsWith('/admin/recovery/trash/')&&options)return {items:[{id:'r1',state:path.endsWith('restore')?'restored':'purged'}]}
 if(path==='/admin/recovery/history/r1?page=1')return {current:{...structuredClone(record),deleted_at:null},items:[{number:1,created_at:'2026-10-18'}],total:1}
 if(path==='/admin/recovery/history/r1/1')return {number:1,snapshot:structuredClone(record),scope:{content:true,template:false,connections:false,life:false},can_restore_full:false}
 if(path.endsWith('/restore')&&options)return {}
 if(path==='/admin/maintenance/settings')return {cleanup_confirmed:false,retention_days:30,backup_enabled:true,frequency:'weekly',weekday:0,hour:3,minute:0,timezone:'Asia/Shanghai',keep:8,revision:1}
 if(path==='/admin/maintenance/status')return {online:true,configured:false,now:'2026-10-19T00:00:00Z'}
 if(path==='/admin/maintenance/jobs'||path==='/admin/maintenance/backups')return []
 throw Error(path)
})})
afterEach(()=>{app?.unmount();root.remove();vi.restoreAllMocks()})
it('lists trash details and restores without sending shared-resource deletes',async()=>{await mount(TrashAdmin);expect(root.textContent).toContain('虚构故事');button('查看删除记录').click();await flush();expect(root.textContent).toContain('导航仍引用');button('恢复记录').click();await flush();const call=api.request.mock.calls.find(([p,o])=>p==='/admin/recovery/trash/restore'&&o);expect(JSON.parse(String(call?.[1]?.body))).toEqual({items:[{id:'r1',expected_revision:2}],confirmation:'恢复'});expect(root.textContent).toContain('记录已恢复')})
it('requires a second typed confirmation for permanent deletion',async()=>{await mount(TrashAdmin);vi.mocked(window.prompt).mockReturnValue('取消');button('永久删除记录').click();await flush();expect(api.request.mock.calls.some(([p,o])=>p.endsWith('/purge')&&o)).toBe(false);vi.mocked(window.prompt).mockReturnValue('永久删除');button('永久删除记录').click();await flush();expect(api.request.mock.calls.some(([p,o])=>p.endsWith('/purge')&&o?.method==='POST')).toBe(true)})
it('shows readable historical scope and restores only available fields as a new draft',async()=>{await mount(HistoryView,'/admin/history/r1');button('修订 12026-10-18').click();await flush();expect(root.querySelectorAll('.snapshot')).toHaveLength(2);expect(root.textContent).toContain('未记录的数据无法从该版本恢复');expect(root.querySelectorAll('select[aria-label="恢复范围"] option')).toHaveLength(1);button('恢复此版本为新草稿').click();await flush();const call=api.request.mock.calls.find(([p,o])=>p==='/admin/recovery/history/r1/1/restore'&&o);expect(JSON.parse(String(call?.[1]?.body))).toEqual({expected_revision:2,scope:'content',confirmation:'恢复为新草稿'});expect(root.textContent).toContain('新的草稿修订')})
it('never presents an unconfigured SSD as a successful backup',async()=>{await mount(MaintenanceAdmin);expect(root.textContent).toContain('备份目录或应用版本未配置');expect((button('立即完整备份') as HTMLButtonElement).disabled).toBe(true);expect(root.textContent).toContain('尚无成功备份');expect(root.textContent).toContain('网页不能提交宿主机路径')})
it('preserves unsaved maintenance settings after a server conflict',async()=>{await mount(MaintenanceAdmin);const input=root.querySelector<HTMLInputElement>('input[type=number]')!;input.value='4';input.dispatchEvent(new Event('input',{bubbles:true}));await nextTick();api.request.mockImplementationOnce(async()=>{throw Error('配置已更新')});button('保存维护设置').click();await flush();expect(input.value).toBe('4');expect(root.textContent).toContain('设置输入保留');expect(root.textContent).toContain('有未保存修改')})

it('requires explicit policy review before enabling cleanup',async()=>{await mount(MaintenanceAdmin);expect(root.textContent).toContain('自动清理已暂停');expect((button('按保留策略立即清理') as HTMLButtonElement).disabled).toBe(true);const box=root.querySelector<HTMLInputElement>('[aria-label="确认已审核清理策略"]')!;expect(box.checked).toBe(false);box.click();await nextTick();expect(root.textContent).toContain('有未保存修改');expect((button('按保留策略立即清理') as HTMLButtonElement).disabled).toBe(true)})

it('sends explicit Phase4A cleanup review only after checking the safety control',async()=>{
 await mount(MaintenanceAdmin)
 const box=root.querySelector<HTMLInputElement>('[aria-label="确认已审核清理策略"]')!
 expect(box.checked).toBe(false)
 box.click();await nextTick();button('保存维护设置').click();await flush()
 const call=api.request.mock.calls.find(([path,options])=>path==='/admin/maintenance/settings'&&options?.method==='PUT')!
 const payload=JSON.parse(call[1]!.body as string)
 expect(payload.cleanup_confirmed).toBe(true)
 expect(payload.cleanup_reviewed).toBe(true)
 // The mock server still returns paused: UI must use server state, not assume activation.
 expect(box.checked).toBe(false)
})

it('separates mixed purge results into accessible success and failure groups',async()=>{
 const original=api.request.getMockImplementation()!
 api.request.mockImplementation(async(path:string,options?:RequestInit)=>{
  if(path.startsWith('/admin/recovery/trash?'))return {items:[structuredClone(record),{...structuredClone(record),id:'r2',title:'合成受保护文章'}],total:2}
  if(path==='/admin/recovery/trash/purge'&&options)return {items:[{id:'r1',state:'purged'},{id:'r2',state:'failed',status:409,code:'dependency_conflict',error:'导航仍引用此记录'}]}
  return original(path,options)
 })
 await mount(TrashAdmin)
 for(const box of Array.from(root.querySelectorAll<HTMLInputElement>('.trash-row input[type=checkbox]')))box.click()
 await nextTick();button('永久删除所选').click();await flush();await flush()
 const success=root.querySelector('[aria-label="操作成功"]')!,failure=root.querySelector('[aria-label="操作失败"]')!
 expect(success.getAttribute('role')).toBe('status');expect(success.textContent).toContain('成功 1 篇');expect(success.textContent).not.toContain('导航仍引用')
 expect(failure.getAttribute('role')).toBe('alert');expect(failure.textContent).toContain('合成受保护文章');expect(failure.textContent).toContain('dependency_conflict')
 expect(root.textContent).toContain('08:00:00');expect(root.textContent).not.toContain('2026-10-19T00:00:00Z')
})
