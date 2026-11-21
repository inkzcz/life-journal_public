// @vitest-environment jsdom
import {createApp,nextTick} from 'vue'
import {it,expect,vi} from 'vitest'
import PlaceActions from './PlaceActions.vue'
const api=vi.hoisted(()=>({request:vi.fn()}));vi.mock('../api',()=>api)
it('shows local duplicate preview before explicit merge and preserves version checks',async()=>{
 const source={id:'source',name:'合成地点',revision:4},target={id:'target',name:'合成地点',revision:7};api.request.mockImplementation(async(p:string)=>p.endsWith('/duplicates')?[target]:{source,target,references:[{kind:'历史修订',title:'旧故事',revision:1}]})
 vi.spyOn(window,'confirm').mockReturnValue(true);const root=document.createElement('div');document.body.append(root);const app=createApp(PlaceActions,{place:source,disabled:false});app.mount(root)
 const flush=async()=>{await new Promise(r=>setTimeout(r,0));await nextTick()},button=(s:string)=>Array.from(root.querySelectorAll('button')).find(b=>b.textContent?.includes(s))!
 button('查找重复候选').click();await flush();button('合成地点 ·').click();await flush();expect(root.textContent).toContain('旧故事');expect(api.request.mock.calls.some(([p])=>p.endsWith('/merge'))).toBe(false)
 button('确认合并地点').click();await flush();const call=api.request.mock.calls.find(([p])=>p.endsWith('/merge'))!;expect(JSON.parse(String(call[1]?.body))).toEqual({target_id:'target',expected_revision:4,target_revision:7,confirmation:'合并地点'})
 app.unmount();root.remove();vi.restoreAllMocks()
})
