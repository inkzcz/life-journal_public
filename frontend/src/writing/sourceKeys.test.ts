import {describe,it,expect} from 'vitest'
import {sourceEdit} from './sourceKeys'
describe('lossless Markdown keys',()=>{
 it('continues nested food descriptions without creating a top-level item',()=>{expect(sourceEdit('- @f 小店\n  - 好吃',14,14,'Enter')?.text).toBe('- @f 小店\n  - 好吃\n  - ')})
 it('increments numbered lists and resets task checks',()=>{expect(sourceEdit('9. done',7,7,'Enter')?.text).toBe('9. done\n10. ');expect(sourceEdit('- [x] done',10,10,'Enter')?.text).toBe('- [x] done\n- [ ] ')})
 it('indents and reverses selected lines',()=>{const x=sourceEdit('one\ntwo',0,7,'Tab')!;expect(x.text).toBe('  one\n  two');expect(sourceEdit(x.text,0,x.text.length,'Tab',true)?.text).toBe('one\ntwo')})
 it('leaves ordinary Enter untouched and wraps only selection',()=>{expect(sourceEdit('plain',5,5,'Enter')).toBeUndefined();expect(sourceEdit('abcd',1,3,'b',false,true)?.text).toBe('a**bc**d')})
})

it('leaves versioned media metadata unchanged when Tab intersects its JSON',()=>{
 const text='- 旅行\n\n  :::lj-media-v1\n  {"id":"11111111-1111-4111-8111-111111111111","caption":"说明"}\n  :::\n'
 const start=text.indexOf('caption'),end=start+7
 expect(sourceEdit(text,start,end,'Tab',false,false,2)).toEqual({text,start,end})
 expect(sourceEdit(text,0,text.length,'Tab',true,false,2)?.text).toBe(text)
})
