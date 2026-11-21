// @vitest-environment jsdom
import {it,expect,vi} from 'vitest'
import {Slice,Fragment} from '@tiptap/pm/model'
import {Editor} from '@tiptap/core'
import {writingExtensions} from './extensions'
import {serializeEntry,blankEntry,readEntry,type Entry} from './entries'
import {bodyTree,visualCompatible} from './body'
vi.mock('../api',()=>({request:vi.fn()}))
const a:Entry={id:'11111111-1111-4111-8111-111111111111',kind:'f',name:'合成餐厅',fields:{review:'不依赖缩进'},media_ids:['22222222-2222-4222-8222-222222222222']}
it('roundtrips stable source identity, typed fields and explicit media through TipTap Markdown',()=>{
 const src='开头\n\n'+serializeEntry(a)+'\n\n结尾';expect(visualCompatible(src)).toBe(true)
 const e=new Editor({extensions:writingExtensions(),content:src,contentType:'markdown'})
 try{const out=e.getMarkdown();expect(readEntry(out.slice(out.indexOf(':::lj-entry-v1')))?.attrs).toEqual(a);expect(out).toContain('开头');expect(out).toContain('结尾');expect(bodyTree(out,2).find(n=>n.entry)?.entry).toEqual(a)}finally{e.destroy()}
})
it('keeps malformed/unknown card source outside visual mode instead of dropping payloads',()=>{
 for(const src of [':::lj-entry-v1\n{bad}\n:::',':::lj-entry-v2\n{}\n:::'])expect(visualCompatible(src)).toBe(false)
})
it('keeps literal code inert and creates unique identities for independently authored same-name entries',()=>{
 const b=blankEntry(),c=blankEntry();expect(b.id).not.toBe(c.id)
 const tree=bodyTree('```\n'+serializeEntry(a)+'\n```',2);expect(tree.some(n=>n.entry)).toBe(false)
})

it('preserves identity on a local drag move but assigns a new ID when a visual card is pasted',()=>{
 const e=new Editor({extensions:writingExtensions(),content:'前文\n\n'+serializeEntry(a)+'\n\n后文',contentType:'markdown'})
 try{
  const atom=e.schema.nodes.lifeEntry!.create({value:a}),slice=new Slice(Fragment.from(atom),0,0)
  const html=e.getHTML();expect(html).toContain('data-life-entry-v1')
  let handled=false;e.view.someProp('handleDrop',handler=>{handled=handler(e.view,{clientX:0,clientY:0} as DragEvent,slice,true)||false;return handled})
  expect(handled).toBe(false);expect(slice.content.firstChild?.attrs.value.id).toBe(a.id)
  e.commands.setTextSelection(e.state.doc.content.size-1)
  e.view.someProp('handlePaste',handler=>handler(e.view,{} as ClipboardEvent,slice))
  const found:string[]=[];e.state.doc.descendants(n=>{if(n.type.name==='lifeEntry')found.push(n.attrs.value.id)})
  expect(found).toHaveLength(2);expect(found).toContain(a.id);expect(new Set(found).size).toBe(2)
 }finally{e.destroy()}
})

it.each(['- ','1. ','10. '])('roundtrips a card-only %s list item without dropping its stable ID',prefix=>{
 const src=prefix+serializeEntry(a).split('\n').join('\n'+' '.repeat(prefix.length))
 const e=new Editor({extensions:writingExtensions(),content:src,contentType:'markdown'})
 try{const out=e.getMarkdown();const ids:string[]=[];const walk=(nodes:any[])=>nodes.forEach(n=>{if(n.entry)ids.push(n.entry.id);if(n.children)walk(n.children)});walk(bodyTree(out,2));expect(ids,out).toEqual([a.id]);expect(visualCompatible(out)).toBe(true)}finally{e.destroy()}
})
