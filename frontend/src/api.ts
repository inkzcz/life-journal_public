let csrf = ''
// Share the initial CSRF request across parallel thumbnails; retain write protection.
let initializing:Promise<void>|undefined
async function initCsrf(){
 if(csrf)return
 if(!initializing)initializing=(async()=>{
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000)
  try{const r=await fetch('/api/auth/csrf',{credentials:'same-origin',signal:controller.signal});if(!r.ok)throw new Error('无法初始化安全令牌');const value=(await r.json()).csrf_token;if(typeof value!=='string'||!value)throw new Error('安全令牌响应无效');csrf=value}
  finally{clearTimeout(timer)}
 })().finally(()=>{initializing=undefined})
 await initializing
}
export async function request(path: string, options: RequestInit = {}) {
  await initCsrf()
  const headers = new Headers(options.headers)
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  if (options.method && !['GET','HEAD'].includes(options.method.toUpperCase())) headers.set('X-CSRF-Token',csrf)
  const response = await fetch('/api'+path, {...options, headers, credentials:'same-origin'})
  if (response.status === 401) { csrf=''; window.dispatchEvent(new Event('session-expired',{cancelable:true})) }
  if (!response.ok) { let msg='请求失败',detail:any; try { detail=(await response.json()).detail; msg=typeof detail==='string'?detail:Array.isArray(detail)?detail.map((item:{msg?:string})=>item.msg||'输入无效').join('；'):detail?.message?[detail.message,...(detail.blocked||[]).map((item:{id:string;reason:string})=>item.id+'：'+item.reason)].join('；'):msg } catch {} ; throw Object.assign(new Error(msg),{status:response.status,detail}) }
  return response.headers.get('content-type')?.includes('application/json') ? response.json() : response.blob()
}
export async function privateImage(id: string): Promise<string> {
  const blob = await request('/media/'+id)
  return URL.createObjectURL(blob as Blob)
}

// XHR exposes true upload progress while reusing the same session and CSRF token.
export async function uploadImage(path:string,body:FormData,key:string,signal:AbortSignal,progress:(value:number)=>void):Promise<any>{
 if(signal.aborted)throw new DOMException('上传已取消或超时','AbortError')
 // Do not cancel the shared CSRF request used by other callers, but never let
 // a stalled initialization prevent this upload from timing out safely.
 await new Promise<void>((resolve,reject)=>{
  const abort=()=>reject(new DOMException('上传已取消或超时','AbortError'))
  signal.addEventListener('abort',abort,{once:true})
  initCsrf().then(()=>{signal.removeEventListener('abort',abort);resolve()},e=>{signal.removeEventListener('abort',abort);reject(e)})
 })
 return new Promise((resolve,reject)=>{
  const xhr=new XMLHttpRequest()
  const fail=(message:string)=>reject(new Error(message))
  const abort=()=>xhr.abort()
  xhr.open('POST','/api'+path);xhr.withCredentials=true
  xhr.setRequestHeader('X-CSRF-Token',csrf);xhr.setRequestHeader('X-Upload-Key',key)
  xhr.upload.onprogress=e=>{if(e.lengthComputable)progress(Math.round(e.loaded/e.total*100))}
  xhr.onload=()=>{signal.removeEventListener('abort',abort);let data:any;try{data=JSON.parse(xhr.responseText)}catch{return fail('上传响应无效，可使用原请求重试核对')}
   if(xhr.status===403)csrf=''
   if(xhr.status===401){csrf='';window.dispatchEvent(new Event('session-expired',{cancelable:true}))}
   if(xhr.status>=200&&xhr.status<300)resolve(data);else fail(typeof data.detail==='string'?data.detail:'上传失败，请使用原上传项重试')}
  xhr.onerror=()=>{signal.removeEventListener('abort',abort);fail('网络中断，上传结果尚未确认；重试可安全核对')}
  xhr.onabort=()=>{signal.removeEventListener('abort',abort);reject(new DOMException('上传已取消或超时','AbortError'))}
  if(signal.aborted){reject(new DOMException('上传已取消或超时','AbortError'));return}
  signal.addEventListener('abort',abort,{once:true});xhr.send(body)
 })
}
