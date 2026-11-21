// @vitest-environment jsdom
import {it,expect,vi,afterEach} from 'vitest'
afterEach(()=>{vi.unstubAllGlobals();vi.resetModules()})
it('aborts before any upload when the shared CSRF initialization stalls',async()=>{
 vi.resetModules();vi.stubGlobal('fetch',vi.fn(()=>new Promise(()=>{})))
 const {uploadImage}=await import('./api');const abort=new AbortController()
 const request=uploadImage('/admin/archive/media',new FormData(),'synthetic',abort.signal,()=>{})
 abort.abort();await expect(request).rejects.toMatchObject({name:'AbortError'})
},1000)
it('already aborted uploads never start a CSRF request',async()=>{
 vi.resetModules();const fetch=vi.fn();vi.stubGlobal('fetch',fetch)
 const {uploadImage}=await import('./api');const abort=new AbortController();abort.abort()
 await expect(uploadImage('/admin/archive/media',new FormData(),'synthetic',abort.signal,()=>{})).rejects.toMatchObject({name:'AbortError'});expect(fetch).not.toHaveBeenCalled()
})
