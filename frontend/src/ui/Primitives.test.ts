// @vitest-environment jsdom
import {createApp,h,nextTick} from 'vue'
import {createRouter,createMemoryHistory} from 'vue-router'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import ConfirmHost from './ConfirmHost.vue'
import UiButton from './UiButton.vue'
import UiPanel from './UiPanel.vue'
import UiState from './UiState.vue'
import {confirmAction,promptAction} from './confirm'
let cleanup=()=>{}
beforeEach(()=>{if(!HTMLDialogElement.prototype.showModal)Object.defineProperty(HTMLDialogElement.prototype,'showModal',{configurable:true,value:function(){}});if(!HTMLDialogElement.prototype.close)Object.defineProperty(HTMLDialogElement.prototype,'close',{configurable:true,value:function(){}});vi.spyOn(HTMLDialogElement.prototype,'showModal').mockImplementation(function(this:HTMLDialogElement){this.open=true});vi.spyOn(HTMLDialogElement.prototype,'close').mockImplementation(function(this:HTMLDialogElement){this.open=false;this.dispatchEvent(new Event('close'))})})
afterEach(()=>{cleanup();vi.restoreAllMocks()})
async function mount(){const root=document.createElement('div');document.body.append(root);const router=createRouter({history:createMemoryHistory(),routes:[{path:'/:all(.*)*',component:{template:'<div/>'}}]});await router.push('/');await router.isReady();const app=createApp(ConfirmHost);app.use(router);app.mount(root);cleanup=()=>{app.unmount();root.remove()};return router}
it('requires an explicit choice, preserves full warning text and safely cancels',async()=>{
 await mount();const pending=confirmAction('永久删除：历史引用必须检查，无法恢复。');await nextTick();await nextTick();const dialog=document.querySelector('.ui-confirm')!;expect(dialog.textContent).toContain('历史引用必须检查');expect(document.activeElement?.textContent).toBe('取消操作');(dialog.querySelector('.quiet') as HTMLButtonElement).click();expect(await pending).toBe(false)
})
it('keeps typed second confirmation and cancels queued operations on route changes',async()=>{
 const router=await mount();const pending=promptAction('请输入永久删除');await nextTick();await nextTick();const input=document.querySelector<HTMLInputElement>('.ui-confirm input')!;input.value='永久删除';input.dispatchEvent(new Event('input',{bubbles:true}));(document.querySelector('.ui-confirm .danger') as HTMLButtonElement).click();expect(await pending).toBe('永久删除')
 const next=confirmAction('不得在新页面执行旧操作');await nextTick();await router.push('/next');await nextTick();expect(await next).toBe(false)
})
it('shared button loading, panel, status and empty/error states retain native semantics',()=>{
 const root=document.createElement('div'),click=vi.fn();document.body.append(root);const app=createApp({render:()=>h(UiPanel,{title:'共享面板'},()=>[h(UiButton,{busy:true,onClick:click},()=> '保存'),h(UiState,{kind:'error',title:'未保存'},()=> '输入保留'),h(UiState,{kind:'loading'},()=> '正在读取'),h(UiState,{},()=> '没有内容')])});app.mount(root);expect(root.querySelector('button')?.disabled).toBe(true);root.querySelector('button')!.click();expect(click).not.toHaveBeenCalled();expect(root.querySelector('[role=alert]')?.textContent).toContain('输入保留');expect(root.querySelector('[role=status]')).not.toBeNull();expect(root.querySelector('.ui-empty')).not.toBeNull();app.unmount();root.remove()
})
