// @vitest-environment jsdom
import {createApp,nextTick,type App} from 'vue'
import {it,expect,vi,afterEach} from 'vitest'
import ResourceManager from './ResourceManager.vue'
const api=vi.hoisted(()=>({request:vi.fn()}));vi.mock('../api',()=>api)
let app:App|undefined,root:HTMLElement
const rows=[1,2,3].map(i=>({id:'image-'+i,revision:1,title:'合成'+i,filename:'synthetic.png',alt:'',created_at:'2026-10-22',width:10,height:10}))
const flush=async()=>{await new Promise(r=>setTimeout(r,0));await nextTick()}
afterEach(()=>{app?.unmount();root?.remove();vi.restoreAllMocks()})
it('supports current-page select all, Shift range and explicit atomic batch payload',async()=>{
 vi.spyOn(window,'confirm').mockReturnValue(true);api.request.mockReset().mockImplementation(async(path:string,options?:RequestInit)=>path==='/admin/archive/folders'?[]:path==='/admin/archive/media-batch'?{items:rows}:path.startsWith('/admin/archive/media?')?{items:rows,total:3}:new Blob())
 root=document.createElement('div');document.body.append(root);app=createApp(ResourceManager,{mode:'media'});app.mount(root);await flush()
 const checks=root.querySelectorAll<HTMLInputElement>('.media-grid input[type=checkbox]');checks[0]!.click();checks[2]!.dispatchEvent(new MouseEvent('click',{bubbles:true,shiftKey:true}));await nextTick();expect(root.textContent).toContain('已选 3 张')
 Array.from(root.querySelectorAll('button')).find(b=>b.textContent?.trim()==='批量移动')!.click();await flush()
 const call=api.request.mock.calls.find(([p])=>p==='/admin/archive/media-batch')!;expect(JSON.parse(String(call[1]?.body))).toMatchObject({action:'move',folder_id:null,confirmation:'执行批量操作',items:rows.map(r=>({id:r.id,expected_revision:1}))});expect(root.textContent).toContain('已选 0 张')
})
it('clears the selected folder identity after rename so new-folder mode is not misleading',async()=>{
 const FolderManager=(await import('./FolderManager.vue')).default
 const folder={id:'folder',name:'原名称',parent_id:null,revision:1}
 api.request.mockReset().mockImplementation(async(path:string,options?:RequestInit)=>{if(options?.method==='PUT')return {...folder,name:'新名称',revision:2};return [folder]})
 root=document.createElement('div');document.body.append(root);app=createApp(FolderManager);app.mount(root);await flush()
 const choose=root.querySelector<HTMLSelectElement>('select[aria-label="选择要编辑的文件夹"]')!;choose.value='folder';choose.dispatchEvent(new Event('change',{bubbles:true}));await nextTick()
 const name=root.querySelector<HTMLInputElement>('input')!;name.value='新名称';name.dispatchEvent(new Event('input',{bubbles:true}));await nextTick();Array.from(root.querySelectorAll('button')).find(b=>b.textContent==='保存文件夹')!.click();await flush()
 expect(api.request.mock.calls.some(([p,o])=>p==='/admin/archive/folders/folder'&&o?.method==='PUT')).toBe(true);expect(choose.value).toBe('');expect(name.value).toBe('')
})

it('media library unfiled upload explicitly opts out of automatic archive rules',async()=>{
 api.request.mockReset().mockImplementation(async(path:string,options?:RequestInit)=>path==='/admin/archive/folders'?[]:path.startsWith('/admin/archive/media?')?{items:[],total:0}:path==='/admin/archive/media'?{id:'synthetic-upload'}:[])
 root=document.createElement('div');document.body.append(root);app=createApp(ResourceManager,{mode:'media'});app.mount(root);await flush()
 const folder=root.querySelector<HTMLSelectElement>('select[aria-label="按文件夹浏览"]')!;folder.value='';folder.dispatchEvent(new Event('change',{bubbles:true}));await flush()
 const upload=root.querySelector<HTMLInputElement>('input[type=file]')!;Object.defineProperty(upload,'files',{value:[new File(['synthetic'],'test.png',{type:'image/png'})]});upload.dispatchEvent(new Event('change',{bubbles:true}));await flush()
 const call=api.request.mock.calls.find(([p,o])=>p==='/admin/archive/media'&&o?.method==='POST')!;expect(call).toBeTruthy();expect((call[1]!.body as FormData).get('auto_archive')).toBe('false')
})
