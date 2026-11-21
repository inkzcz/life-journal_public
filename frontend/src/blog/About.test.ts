// @vitest-environment jsdom
import {it,expect,vi,afterEach} from 'vitest'
import {createApp,nextTick,type App} from 'vue'
import About from './AboutPage.vue'
import {consistency} from '../buildInfo'
import {VERSION} from '../version'
const about={name:'合成档案馆',intro:'测试简介',body:'## 合成内容',motivation:'留住时光',notes:'仅供测试',revision:0}
vi.mock('../api',()=>({request:vi.fn(async(p:string,o:any)=>p==='/blog/about'?about:p==='/blog/build-info'?{version:VERSION,short_revision:'abcdef0',revision_verified:false,source_kind:'user-provided-zip',changelog:[]}:p==='/admin/status'?{is_admin:true}:p==='/admin/blog/about'?{...JSON.parse(o.body),revision:1}:p==='/blog/site'?{title:'Life Journal',appearance:{theme:'modern',mode:'light'},sections:[],navigation:[]}:{} )}))
let app:App,root:HTMLDivElement
afterEach(()=>{app?.unmount();root?.remove()})
it('shows truthful ZIP identity, previews and cancels without a write',async()=>{
 root=document.createElement('div');document.body.append(root);app=createApp(About);app.component('RouterLink',{template:'<a><slot/></a>'});app.mount(root);await new Promise(r=>setTimeout(r,20));await nextTick()
 expect(root.textContent).toContain('ZIP 声明 SHA，未经 Git 验证');expect(root.querySelector('h2')?.textContent).toBe('合成档案馆')
 Array.from(root.querySelectorAll('button')).find(b=>b.textContent==='编辑网站介绍')!.click();await nextTick();const input=root.querySelector('input')!;input.value='未保存内容';input.dispatchEvent(new Event('input',{bubbles:true}));Array.from(root.querySelectorAll('button')).find(b=>b.textContent==='取消介绍修改')!.click();await nextTick();expect(root.querySelector('h2')?.textContent).toBe('合成档案馆')
})
it('does not claim a frontend/API match without baked provenance',()=>{expect(consistency({version:VERSION,short_revision:null,built_at:null,revision_verified:false,source_kind:'unversioned',fingerprint:null})).toContain('尚未验证')})

it('labels matching declared metadata as an identity comparison, never image verification',async()=>{
 const info=await import('../buildInfo');const previous=info.WEB_BUILD.fingerprint;info.WEB_BUILD.fingerprint='same-declared-metadata'
 try{const message=consistency({...info.WEB_BUILD,revision_verified:false,source_kind:'user-provided-zip'});expect(message).toContain('构建标识一致');expect(message).toContain('非镜像完整性校验');expect(consistency({...info.WEB_BUILD,fingerprint:'different'})).toContain('不一致');expect(consistency({...info.WEB_BUILD,version:'0.0.0'})).toContain('版本不一致')}finally{info.WEB_BUILD.fingerprint=previous}
})

it('sanitizes About Markdown and hides editing and private diagnostics from readers',async()=>{
 const {request}=await import('../api');const original=vi.mocked(request).getMockImplementation()!
 vi.mocked(request).mockImplementation(async(p:string,o:any)=>p==='/admin/status'?{is_admin:false}:p==='/blog/about'?{...about,body:'<script>alert(1)</script><a href="javascript:alert(1)">bad</a>\n\n正常正文'}:original(p,o))
 try{root=document.createElement('div');document.body.append(root);app=createApp(About);app.component('RouterLink',{template:'<a><slot/></a>'});app.mount(root);await new Promise(r=>setTimeout(r,20));await nextTick();expect(root.querySelector('script')).toBeNull();expect(root.querySelector('[href^="javascript:"]')).toBeNull();expect(root.textContent).toContain('正常正文');expect(root.textContent).not.toContain('编辑网站介绍');expect(root.textContent).not.toContain('管理员构建诊断')}finally{vi.mocked(request).mockImplementation(original)}
})
