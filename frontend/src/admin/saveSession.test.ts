import { it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createSaveSession } from './saveSession'
let text:string, id:string|undefined, reason:string
const deferred=()=>{let resolve!:(v:any)=>void,reject!:(e:any)=>void;const promise=new Promise<any>((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject}}
function setup(persist=vi.fn(async(snapshot:string,revision:number,_signal:AbortSignal)=>({snapshot,revision:revision+1}))){
 const accept=vi.fn((r:any)=>r)
 const session=createSaveSession({snapshot:()=>text,identity:()=>id,enabled:()=>true,blocked:()=>reason,persist,accept})
 session.begin(text,1);return {session,persist,accept}
}
beforeEach(()=>{vi.useFakeTimers();text='initial';id='one';reason=''})
afterEach(()=>{vi.useRealTimers();vi.restoreAllMocks()})
it('does not save initial or unchanged snapshots; debounces continuous edits',async()=>{
 const {session,persist}=setup();session.changed();await vi.advanceTimersByTimeAsync(4000);expect(persist).not.toHaveBeenCalled()
 text='first';session.changed();await vi.advanceTimersByTimeAsync(2500);text='latest';session.changed();await vi.advanceTimersByTimeAsync(2999);expect(persist).not.toHaveBeenCalled()
 await vi.advanceTimersByTimeAsync(1);expect(persist).toHaveBeenCalledTimes(1);expect(persist.mock.calls[0]?.slice(0,2)).toEqual(['latest',1]);expect(session.state.revision).toBe(2);expect(session.dirty()).toBe(false);expect(session.state.status).toBe('saved')
})
it('keeps in-flight input and serializes a later save with the returned revision',async()=>{
 const d=deferred(),persist=vi.fn().mockReturnValueOnce(d.promise).mockImplementation(async(snapshot,revision)=>({snapshot,revision:revision+1}))
 const {session}=setup(persist);text='sent';session.changed();await vi.advanceTimersByTimeAsync(3000)
 text='typed during request';session.changed();await vi.advanceTimersByTimeAsync(6000);expect(persist).toHaveBeenCalledTimes(1);expect(session.dirty()).toBe(true)
 d.resolve({snapshot:'sent',revision:2});await vi.advanceTimersByTimeAsync(0);expect(session.state.confirmed).toBe('sent');expect(text).toBe('typed during request')
 await vi.advanceTimersByTimeAsync(3000);expect(persist).toHaveBeenCalledTimes(2);expect(persist.mock.calls[1]?.slice(0,2)).toEqual(['typed during request',2]);expect(session.state.revision).toBe(3)
})
it.each([401,403,404,409,422,500,0])('pauses after %s failure without losing input or advancing revision',async(status)=>{
 const persist=vi.fn().mockRejectedValue(Object.assign(new Error('failure'),{status}));const {session}=setup(persist)
 text='unsaved';session.changed();await vi.advanceTimersByTimeAsync(3000)
 expect(session.state.revision).toBe(1);expect(session.state.confirmed).toBe('initial');expect(text).toBe('unsaved');expect(session.dirty()).toBe(true);expect(session.state.paused).toBe(true)
 text='still editable';session.changed();await vi.advanceTimersByTimeAsync(9000);expect(persist).toHaveBeenCalledTimes(1)
 if(status===409){expect(session.state.status).toBe('conflict');expect(await session.save('manual')).toBe(false);expect(persist).toHaveBeenCalledTimes(1)}
})
it('allows explicit retry after validation/network failure but never silent revision rebasing',async()=>{
 const persist=vi.fn().mockRejectedValueOnce(new Error('offline')).mockImplementation(async(snapshot,revision)=>({snapshot,revision:revision+1}));const {session}=setup(persist)
 text='retained';expect(await session.save('manual')).toBe(false);expect(await session.save('manual')).toBe(true);expect(persist.mock.calls[1]?.[1]).toBe(1);expect(session.state.revision).toBe(2)
})
it('cannot autosave new records or published changes, but manual draft creation is available',async()=>{
 id=undefined;reason='first create';const {session,persist}=setup();text='new';session.changed();await vi.advanceTimersByTimeAsync(5000);expect(persist).not.toHaveBeenCalled();expect(session.state.status).toBe('blocked')
 expect(await session.save('manual')).toBe(true);id='created';reason='published';text='published change';session.changed();await vi.advanceTimersByTimeAsync(5000);expect(persist).toHaveBeenCalledTimes(1);expect(await session.save('auto')).toBe(false)
})
it('prevents duplicate POST after uncertain creation',async()=>{
 id=undefined;reason='first create';const {session,persist}=setup(vi.fn().mockRejectedValue(new Error('network')))
 text='new';await session.save('manual');expect(session.state.uncertainCreation).toBe(true);expect(await session.save('manual')).toBe(false);expect(persist).toHaveBeenCalledTimes(1)
})
it('ignores old responses after switching target and preserves the new session state',async()=>{
 const d=deferred(),{session,accept}=setup(vi.fn().mockReturnValue(d.promise));text='old edit';const pending=session.save('manual')
 id='two';text='new record';session.begin(text,7);d.resolve({snapshot:'old edit',revision:2});expect(await pending).toBe(false);expect(accept).not.toHaveBeenCalled();expect(session.state.revision).toBe(7);expect(session.state.confirmed).toBe('new record')
})
it('clears debounce on disposal and ignores a response after unmount',async()=>{
 const {session,persist}=setup();text='edit';session.changed();session.stop();await vi.advanceTimersByTimeAsync(5000);expect(persist).not.toHaveBeenCalled()
 const d=deferred(),next=setup(vi.fn().mockReturnValue(d.promise));text='unmounted change';const pending=next.session.save('manual');next.session.stop();d.resolve({snapshot:text,revision:2});expect(await pending).toBe(false);expect(next.accept).not.toHaveBeenCalled()
})
it('times out, aborts the client request, and does not retry automatically',async()=>{
 const {session,persist}=setup(vi.fn().mockReturnValue(new Promise(()=>{})));text='pending';const pending=session.save('manual');await vi.advanceTimersByTimeAsync(15000);expect(await pending).toBe(false)
 expect((persist.mock.calls[0]?.[2] as AbortSignal).aborted).toBe(true);expect(session.state.status).toBe('error');expect(session.dirty()).toBe(true);await vi.advanceTimersByTimeAsync(9000);expect(persist).toHaveBeenCalledTimes(1)
})
it('treats a request still in flight as unconfirmed even if user undoes the text',async()=>{
 const d=deferred(),{session}=setup(vi.fn().mockReturnValue(d.promise));text='sent';const pending=session.save('manual');text='initial';expect(session.dirty()).toBe(true);d.resolve({snapshot:'sent',revision:2});await pending;expect(session.dirty()).toBe(true)
})
