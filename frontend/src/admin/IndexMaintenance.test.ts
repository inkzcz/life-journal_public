// @vitest-environment jsdom
import {createApp,nextTick} from 'vue'
import {it,expect,vi} from 'vitest'
import IndexMaintenance from './IndexMaintenance.vue'
const api=vi.hoisted(()=>({request:vi.fn()}));vi.mock('../api',()=>api)
vi.mock('../ui/confirm',()=>({confirmAction:vi.fn(async()=>true)}))
const flush=async()=>{await new Promise(r=>setTimeout(r,0));await nextTick()}
it('requires preview and submits its exact digest with explicit confirmation',async()=>{
 const plan={digest:'a'.repeat(64),records:[{record_id:'synthetic',expected_revision:3,indexes:['experiences']}],issues:[],cleanup:[],food_detach:[{id:'food',record_id:'synthetic'}],blocked_food:[],history_references_to_add:0,preserved_food_identities:1,note:'保留手动数据'}
 api.request.mockImplementation(async(path:string)=>path.endsWith('index-preview')?plan:{records:1,cleaned:0,history_references_added:0})
 const root=document.createElement('div');document.body.append(root);const app=createApp(IndexMaintenance);app.mount(root)
 const button=(text:string)=>Array.from(root.querySelectorAll('button')).find(b=>b.textContent?.includes(text))!
 expect(root.textContent).not.toContain('确认重建索引');button('只读检查').click();await flush()
 expect(api.request).toHaveBeenCalledTimes(1);expect(root.textContent).toContain('synthetic');expect(root.textContent).toContain('保留手动数据')
 button('确认重建索引').click();await flush()
 expect(JSON.parse(api.request.mock.calls[1]![1].body)).toEqual({action:'rebuild',digest:plan.digest,confirmation:'确认索引维护'})
 expect(root.textContent).toContain('已完成');expect(root.textContent).not.toContain('确认重建索引');app.unmount();root.remove();api.request.mockReset()
})
it('blocks maintenance while a resource has unsaved edits',()=>{
 const root=document.createElement('div');const app=createApp(IndexMaintenance,{disabled:true});app.mount(root)
 expect(root.querySelector('button')?.disabled).toBe(true);expect(root.textContent).toContain('请先保存或放弃资源草稿');app.unmount()
})


it('explains missing legacy identity and blocks both maintenance actions',async()=>{
 const plan={digest:'a'.repeat(64),records:[],issues:[{record_id:'synthetic',code:'source_not_rebuildable',reason:'missing_legacy_place_binding',status:409}],cleanup:[],food_detach:[],blocked_food:[],history_references_to_add:0,preserved_food_identities:1,note:'身份保留'}
 api.request.mockReset().mockResolvedValue(plan)
 const root=document.createElement('div');document.body.append(root);const app=createApp(IndexMaintenance);app.mount(root)
 root.querySelector('button')!.click();await flush()
 expect(root.querySelector('[role=alert]')?.textContent).toContain('不会按当前同名地点推断')
 const actions=Array.from(root.querySelectorAll('button')).filter(button=>button.textContent?.startsWith('确认'))
 expect(actions).toHaveLength(2)
 for(const action of actions){expect(action.disabled).toBe(true);action.click()}
 await flush();expect(api.request).toHaveBeenCalledTimes(1)
 app.unmount();root.remove();api.request.mockReset()
})
