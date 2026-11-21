// @vitest-environment jsdom
import {it,expect,vi} from 'vitest'
import {newId} from './ids'
it('generates independent RFC4122 v4 identities without secure-context randomUUID',()=>{
 const original=Object.getOwnPropertyDescriptor(crypto,'randomUUID')
 Object.defineProperty(crypto,'randomUUID',{value:undefined,configurable:true})
 try{const ids=new Set(Array.from({length:100},()=>newId()));expect(ids.size).toBe(100);for(const id of ids)expect(id).toMatch(/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/)}finally{if(original)Object.defineProperty(crypto,'randomUUID',original);else delete (crypto as any).randomUUID}
})
it('prefers native randomUUID without calling fallback randomness',()=>{
 const randomUUID=vi.fn(()=>'11111111-1111-4111-8111-111111111111'),getRandomValues=vi.fn()
 vi.stubGlobal('crypto',{randomUUID,getRandomValues})
 try{expect(newId()).toBe('11111111-1111-4111-8111-111111111111');expect(randomUUID).toHaveBeenCalledOnce();expect(getRandomValues).not.toHaveBeenCalled()}finally{vi.unstubAllGlobals()}
})
it('fails closed if the browser has no cryptographically secure primitive',()=>{
 vi.stubGlobal('crypto',{})
 try{expect(()=>newId()).toThrow('浏览器不支持安全随机数')}finally{vi.unstubAllGlobals()}
})
