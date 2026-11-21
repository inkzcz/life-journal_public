// @vitest-environment jsdom
import {createApp,h,nextTick,type App,type Component} from 'vue'
import {beforeEach,afterEach,it,expect,vi} from 'vitest'
import Drafts from './DraftsPage.vue'
import Food from '../life/FoodPage.vue'
import Rules from '../admin/ArchiveRules.vue'
import Resources from './EditorResources.vue'
const {api,push}=vi.hoisted(()=>({api:vi.fn(),push:vi.fn()}))
vi.mock('../api',()=>({request:api}))
vi.mock('../blog/ReaderShell.vue',()=>({default:{template:'<main><slot/><slot name="nav"/></main>'}}))
vi.mock('../admin/FolderSelect.vue',()=>({default:{props:['modelValue'],template:'<select><option>测试文件夹</option></select>'}}))
vi.mock('../admin/PrivatePreview.vue',()=>({default:{template:'<span>私有图片</span>'}}))
vi.mock('vue-router',async()=>({...await vi.importActual('vue-router'),useRouter:()=>({push})}))
let app:App,root:HTMLElement
async function flush(){for(let i=0;i<4;i++){await Promise.resolve();await nextTick()}await new Promise(r=>setTimeout(r,0));await nextTick()}
function mount(component:Component,props={}){root=document.createElement('div');document.body.append(root);app=createApp(component,props);app.component('RouterLink',{props:['to'],setup:(p:any,{slots}:any)=>()=>h('a',{href:p.to},slots.default?.())});app.mount(root)}
async function click(text:string){const b=Array.from(root.querySelectorAll('button')).find(b=>b.textContent===text);expect(b).toBeTruthy();b!.click();await flush()}
async function input(selector:string,value:string){const el=root.querySelector(selector) as HTMLInputElement;el.value=value;el.dispatchEvent(new Event('input',{bubbles:true}));await flush()}
beforeEach(()=>{api.mockReset();push.mockReset();vi.spyOn(window,'confirm').mockReturnValue(true)})
afterEach(()=>{app?.unmount();root?.remove();vi.restoreAllMocks()})
it('draft center uses optimistic delete and never redirects to admin',async()=>{
 api.mockImplementation(async(path:string,options:any)=>path==='/admin/content/types'?[]:path.startsWith('/admin/content/records?')?{items:[{id:'r',title:'合成草稿',summary:'摘要',updated_at:'2026-10-26',type_name:'文章',type_active:true,revision:7}],total:1}:options?.method==='DELETE'?{ok:true}:null)
 mount(Drafts);await flush();expect(root.querySelector('a[href="/write/r"]')).toBeTruthy();expect(root.innerHTML).not.toContain('href="/admin')
 await input('input[type=search]','草稿');root.querySelector('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await flush();expect(api.mock.calls.some(c=>String(c[0]).includes('sort=updated')&&String(c[0]).includes('status=draft'))).toBe(true)
 await click('删除草稿');const call=api.mock.calls.find(c=>c[1]?.method==='DELETE')!;expect(JSON.parse(call[1].body).expected_revision).toBe(7)
})
it('food creation installs an editable template then opens the real writer',async()=>{
 api.mockImplementation(async(path:string)=>path==='/admin/status'?{is_admin:true}:path==='/admin/food/install-template'?{id:'food-template'}:{items:[],total:0})
 mount(Food);await flush();await click('新建美食文章');expect(push).toHaveBeenCalledWith('/write?template=food-template');expect(api.mock.calls.some(c=>c[0]==='/admin/content/records'&&c[1]?.method==='POST')).toBe(false)
})
it('disabled archive rules can preview but cannot execute or delete media',async()=>{
 const rule={id:'rule',revision:1,name:'按月',enabled:false,date_source:'uploaded',fallback:'unknown',granularity:'month',by_type:false,parent_id:null}
 api.mockImplementation(async(path:string,options:any)=>path.endsWith('/preview')?{id:'plan',items:[{id:'m',filename:'图片',path:['2026','10']}]}:options?.method==='POST'?rule:[])
 mount(Rules,{items:[{id:'m',revision:3}]});await flush();await input('input:not([type=checkbox])','按月');await click('保存规则');const create=api.mock.calls.find(c=>c[1]?.method==='POST')!;expect(JSON.parse(create[1].body).enabled).toBe(false)
 await click('预览所选 1 张');expect(Array.from(root.querySelectorAll('button')).find(b=>b.textContent==='确认执行逻辑归档')?.disabled).toBe(true);expect(api.mock.calls.some(c=>String(c[0]).includes('/execute'))).toBe(false)
})
it('marked place removal refuses silent rewriting; library changes require clean editor',async()=>{
 const record={body:'@f 小店',connections:{media:[],places:[{id:'p',name:'小店'}]},marked_places:[{place_id:'p'}],tags:[],body_format:1}
 mount(Resources,{record,dirty:true,disabled:false});await flush();await click('从本文移除');expect(root.textContent).toContain('不会静默改原文');await click('从库中删除');expect(root.textContent).toContain('请先保存或取消');expect(api).not.toHaveBeenCalled()
})

it('food cards show explicit shop/date/address, missing-image placeholder and optional travel source',async()=>{
 const base={record_revision:1,revision:1,city:'合成城',category:'餐厅',article_date:'2026-11-05',day:'2026-10-03',description:'干净摘要',place:null,source_kind:'article',title:'晚餐故事',name:'晚餐故事',shop_name:'合成小馆',address:'合成路12号',travel_source:null}
 api.mockImplementation(async(path:string)=>path==='/admin/status'?{is_admin:false}:{items:[{...base,id:'a',record_id:'r1',cover_id:'own-photo'},{...base,id:'b',record_id:'r2',name:'无图餐厅',source_kind:'mark',shop_name:'无图餐厅',day:null,cover_id:null,travel_source:'合成旅行'}],total:2})
 mount(Food);await flush();expect(root.textContent).toContain('店铺 · 合成小馆');expect(root.textContent).toContain('合成路12号');expect(root.textContent).toContain('2026-10-03');expect(root.querySelectorAll('[aria-label="暂无明确关联图片"]')).toHaveLength(1);expect(root.textContent).toContain('旅行来源：合成旅行');expect(root.textContent).toContain('就餐日期未明确')
})
