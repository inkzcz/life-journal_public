// @vitest-environment jsdom
import {createApp} from 'vue'
import {it,expect} from 'vitest'
import ResourceReferences from './ResourceReferences.vue'
it('keeps historical, inactive, trash and system uses out of current count and groups duplicate index sources',()=>{
 const root=document.createElement('div');document.body.append(root)
 const refs=[{id:'a',title:'合成文章',category:'history',revision:2},{id:'a',title:'合成文章',category:'inactive',kind:'美食索引'},{id:'a',title:'合成文章',category:'inactive',kind:'卡片索引'},{id:'b',title:'合成回收站',category:'trash',deleted:true},{id:'c',title:'合成栏目',category:'system'}]
 const app=createApp(ResourceReferences,{references:refs as any});app.mount(root)
 const text=root.textContent||'';expect(text).toContain('当前有效引用：0');expect(text).toContain('历史版本引用：1');expect(text).toContain('已失效索引：1');expect(text).toContain('回收站引用：1');expect(text).toContain('其他保护引用：1');expect(text).toContain('当前正文已不再使用此资源');expect(text).toContain('修订2')
 expect(Array.from(root.querySelectorAll('button')).find(b=>b.textContent?.includes('合成回收站'))?.disabled).toBe(true)
 app.unmount();root.remove()
})
