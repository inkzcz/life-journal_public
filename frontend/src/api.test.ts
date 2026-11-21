// @vitest-environment jsdom
import {it,expect,vi,afterEach} from 'vitest'
afterEach(()=>{vi.unstubAllGlobals();vi.resetModules()})
it('coalesces simultaneous CSRF initialization and keeps credentials and write protection',async()=>{
 let finish:(r:Response)=>void=()=>{}
 const fetch=vi.fn().mockImplementation((url:string)=>url==='/api/auth/csrf'?new Promise<Response>(resolve=>{finish=resolve}):Promise.resolve(new Response(JSON.stringify({ok:true}),{headers:{'content-type':'application/json'}})))
 vi.stubGlobal('fetch',fetch);const {request}=await import('./api')
 const jobs=[request('/private-a'),request('/private-b'),request('/private-c',{method:'POST',body:'{}'})]
 expect(fetch).toHaveBeenCalledTimes(1);finish(new Response(JSON.stringify({csrf_token:'synthetic-csrf'}),{headers:{'content-type':'application/json'}}));await Promise.all(jobs)
 expect(fetch).toHaveBeenCalledTimes(4)
 for(const [,options] of fetch.mock.calls)expect(options.credentials).toBe('same-origin')
 const write=fetch.mock.calls.find(([url])=>url==='/api/private-c')!;expect(write[1].headers.get('X-CSRF-Token')).toBe('synthetic-csrf')
})
it('allows initialization retry after a failed CSRF request',async()=>{
 const fetch=vi.fn().mockResolvedValueOnce(new Response('',{status:503})).mockResolvedValueOnce(new Response(JSON.stringify({csrf_token:'synthetic'}),{headers:{'content-type':'application/json'}})).mockResolvedValue(new Response('{}',{headers:{'content-type':'application/json'}}))
 vi.stubGlobal('fetch',fetch);const {request}=await import('./api');await expect(request('/private')).rejects.toThrow('无法初始化安全令牌');await expect(request('/private')).resolves.toEqual({});expect(fetch.mock.calls.filter(([url])=>url==='/api/auth/csrf')).toHaveLength(2)
})
