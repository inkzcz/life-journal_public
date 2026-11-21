import {it,expect} from 'vitest'
import {sourceMediaInsertion} from './mediaInsertion'
import {bodyMedia,bodyTree,type MediaBlock} from './body'
const m:MediaBlock={id:'11111111-1111-4111-8111-111111111111',alt:'合成',caption:'',width:960,align:'center'}
it.each([1,2,3])('keeps source insertion inside depth %i restaurant list without replacing its text',depth=>{
 const before=Array.from({length:depth},(_,i)=>'  '.repeat(i)+'- '+(i===depth-1?'@f 合成餐厅':'上层')).join('\n'),source=before+'\n\n末尾'
 const result=sourceMediaInsertion(source,before.length,[m])
 expect(bodyMedia(result.text,2)).toEqual([m]);expect(result.text).toContain('@f 合成餐厅');expect(result.text.endsWith('末尾')).toBe(true)
 let node=bodyTree(result.text,2)[0]!
 for(let i=0;i<depth;i++){expect(node.tag).toBe('ul');const item=node.children![0]!;if(i===depth-1)expect(item.children!.some(n=>n.media?.id===m.id)).toBe(true);else node=item.children!.find(n=>n.tag==='ul')!}
})
it('rejects invalid carets and does not turn code or HTML examples into private references',()=>{
 expect(()=>sourceMediaInsertion('原文',99,[m])).toThrow('位置')
 for(const source of ['```\n代码\n```','<div>示例</div>'])expect(()=>sourceMediaInsertion(source,2,[m])).toThrow('代码或HTML')
})

it.each(['- ','1. ','10. ','-\t'])('inserts directly after an empty %s list marker instead of creating a setext heading or code block',prefix=>{
 const source='- @f 合成餐厅\n  '+prefix
 const result=sourceMediaInsertion(source,source.length,[m,{...m,id:'22222222-2222-4222-8222-222222222222'}])
 expect(bodyMedia(result.text,2).map(x=>x.id),result.text).toEqual([m.id,'22222222-2222-4222-8222-222222222222'])
 expect(result.text).toContain(prefix.replace('\t',' ')+':::lj-media-v1');expect(result.text).toContain('@f 合成餐厅')
})
it('rejects code-level spaces after a marker instead of activating an indented example',()=>{
 const source='-     ';expect(()=>sourceMediaInsertion(source,source.length,[m])).toThrow('属于代码')
})
