// @vitest-environment jsdom
import {it,expect,vi,afterEach} from 'vitest'
import {createApp,nextTick,type App} from 'vue'
import Panel from './TypographyPanel.vue'
import {apply,defaults,saved} from './typography'
vi.mock('../api',()=>({request:vi.fn(async(_p:string,o:any)=>o?{...JSON.parse(o.body),revision:2}:({editor_line:1.5,editor_gap:8,reader_line:null,reader_gap:null,revision:0}))}))
let app:App,root:HTMLDivElement
afterEach(()=>{app?.unmount();root?.remove();saved.value=defaults();apply(defaults())})
it('uses bounded CSS variables, preserving unset legacy reader styles',()=>{apply({...defaults(),editor_line:1.25,reader_gap:4});expect(document.documentElement.style.getPropertyValue('--lj-editor-line')).toBe('1.25');expect(document.documentElement.style.getPropertyValue('--lj-reader-gap')).toBe('4px');apply(defaults());expect(document.documentElement.style.getPropertyValue('--lj-reader-gap')).toBe('')})
it('previews, cancels, saves, and restores defaults without a body model',async()=>{
 root=document.createElement('div');document.body.append(root);app=createApp(Panel);app.mount(root);await new Promise(r=>setTimeout(r,20));await nextTick()
 const select=root.querySelector('select')!;expect(select.getAttribute('aria-label')).toBe('编辑器行距');select.value='1.25';select.dispatchEvent(new Event('change',{bubbles:true}));await nextTick();expect(document.documentElement.style.getPropertyValue('--lj-editor-line')).toBe('1.25')
 function click(text:string){Array.from(root.querySelectorAll('button')).find(b=>b.textContent===text)!.click()}
 click('取消排版修改');await nextTick();expect(select.value).toBe('1.5')
 select.value='2';select.dispatchEvent(new Event('change',{bubbles:true}));await nextTick();click('保存排版');await new Promise(r=>setTimeout(r,10));expect(saved.value.editor_line).toBe(2)
 click('恢复默认排版');await nextTick();expect(select.value).toBe('1.5');expect(saved.value.editor_line).toBe(2)
})

it('blocks edits until delayed preferences load and discards no editable draft',async()=>{
 const {request}=await import('../api');let resolve!:(v:unknown)=>void
 vi.mocked(request).mockImplementationOnce(()=>new Promise(r=>resolve=r))
 // Force a fresh load even if a previous mounted instance filled the shared cache.
 const {loadTypography}=await import('./typography');const loading=loadTypography(true)
 root=document.createElement('div');document.body.append(root);app=createApp(Panel);app.mount(root);await nextTick()
 expect(root.querySelector('fieldset')!.disabled).toBe(true)
 expect(Array.from(root.querySelectorAll('button')).every(b=>b.disabled)).toBe(true)
 resolve({...defaults(),editor_line:2,revision:3});await loading;await nextTick();await nextTick()
 expect(root.querySelector('fieldset')!.disabled).toBe(false);expect(root.querySelector('select')!.value).toBe('2')
})

it('retains a conflicting draft and restores only confirmed preferences on unmount',async()=>{
 const {request}=await import('../api')
 root=document.createElement('div');document.body.append(root);app=createApp(Panel);app.mount(root);await new Promise(r=>setTimeout(r,20))
 const confirmed={...saved.value};const select=root.querySelector('select')!;select.value=confirmed.editor_line===1.25?'2':'1.25';select.dispatchEvent(new Event('change',{bubbles:true}));await nextTick()
 vi.mocked(request).mockRejectedValueOnce(Object.assign(new Error('409：配置已更新'),{status:409}));Array.from(root.querySelectorAll('button')).find(b=>b.textContent==='保存排版')!.click();await new Promise(r=>setTimeout(r,10));expect(root.querySelector('[role=alert]')?.textContent).toContain('409');expect(saved.value).toEqual(confirmed);expect(Number(select.value)).not.toBe(confirmed.editor_line)
 app.unmount();expect(document.documentElement.style.getPropertyValue('--lj-editor-line')).toBe(String(confirmed.editor_line))
})

it('does not apply a pending load to an unmounted panel draft',async()=>{
 const {request}=await import('../api');let resolve!:(v:unknown)=>void;vi.mocked(request).mockImplementationOnce(()=>new Promise(r=>resolve=r));const {loadTypography}=await import('./typography');const loading=loadTypography(true)
 root=document.createElement('div');document.body.append(root);app=createApp(Panel);app.mount(root);await nextTick();app.unmount();resolve({...defaults(),reader_line:1.75,revision:5});await loading;await nextTick();expect(saved.value.reader_line).toBe(1.75);expect(document.documentElement.style.getPropertyValue('--lj-reader-line')).toBe('1.75')
})


it('saves the article mode with typography without modifying appearance or article content',async()=>{
 root=document.createElement('div');document.body.append(root);app=createApp(Panel);app.mount(root);await new Promise(r=>setTimeout(r,20))
 const mode=root.querySelector<HTMLSelectElement>('select[aria-label="默认文章阅读模式"]')!;mode.value='cards';mode.dispatchEvent(new Event('change',{bubbles:true}));await nextTick()
 Array.from(root.querySelectorAll('button')).find(b=>b.textContent==='保存排版')!.click();await new Promise(r=>setTimeout(r,10));expect(saved.value.reader_mode).toBe('cards')
 const {request}=await import('../api');const writes=vi.mocked(request).mock.calls.filter(call=>call[1]);expect(writes.at(-1)?.[0]).toBe('/admin/blog/typography')
})
