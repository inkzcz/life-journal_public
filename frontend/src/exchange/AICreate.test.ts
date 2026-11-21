// @vitest-environment jsdom
import {createApp,h,nextTick,type App} from 'vue'
import {afterEach,it,expect,vi} from 'vitest'
import AICreate from './AICreate.vue'
const api=vi.hoisted(()=>({request:vi.fn()}));vi.mock('../api',()=>api)
vi.mock('vue-router',()=>({onBeforeRouteLeave:vi.fn()}))
const seen=vi.hoisted(()=>({props:null as any,job:''}))
vi.mock('./WritingAssistant.vue',()=>({default:{props:{typeSlug:String,templateSlug:String,title:String,displayDate:String,capture:Function,creation:Boolean},emits:['preview','pending','dirty'],setup(props:any,{emit}:any){seen.props=props;return()=>h('div',[h('button',{onClick:()=>emit('pending',true)},'开始生成'),h('button',{onClick:()=>emit('preview','11111111-1111-4111-8111-111111111111')},'预览候选')])}}}))
vi.mock('./ImportAdmin.vue',()=>({default:{props:['initialJobId'],setup(props:any){seen.job=props.initialJobId;return()=>h('div','复用导入映射与新草稿确认')}}}))
let app:App,root:HTMLElement
const flush=async()=>{for(let i=0;i<6;i++){await Promise.resolve();await nextTick()}}
afterEach(()=>{app?.unmount();root?.remove();vi.clearAllMocks()})
it('uses real active types and matching templates and reuses the import pipeline without creating records',async()=>{
 api.request.mockImplementation(async(path:string)=>path==='/admin/content/types'?[{id:'type-a',slug:'custom-a',name:'用户定义类型',active:true},{id:'type-b',slug:'custom-b',name:'其他类型',active:true}]:[{id:'p',slug:'custom-template',name:'匹配模板',type_id:'type-a',active:true},{id:'q',slug:'wrong-template',name:'别的模板',type_id:'type-b',active:true}])
 root=document.createElement('div');document.body.append(root);app=createApp(AICreate);app.component('RouterLink',{props:['to'],template:'<a :href="to"><slot/></a>'});app.mount(root);await flush()
 expect(seen.props.typeSlug).toBe('custom-a');expect(seen.props.creation).toBe(true);expect(seen.props.title).toBe('');expect(seen.props.displayDate).toBe('');expect(seen.props.capture()).toMatchObject({body:'',selection:'',format:2})
 const options=root.querySelector('select[aria-label="AI创作模板"]')!;expect(options.textContent).toContain('匹配模板');expect(options.textContent).not.toContain('别的模板')
 Array.from(root.querySelectorAll('button')).find(b=>b.textContent==='开始生成')!.click();await flush();expect(root.querySelector('select')!.disabled).toBe(true)
 Array.from(root.querySelectorAll('button')).find(b=>b.textContent==='预览候选')!.click();await flush();expect(seen.job).toBe('11111111-1111-4111-8111-111111111111');expect(root.textContent).toContain('复用导入映射')
 expect(api.request.mock.calls).toHaveLength(2);expect(api.request.mock.calls.every(([,o])=>!o?.method)).toBe(true)
})
