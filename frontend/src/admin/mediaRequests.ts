import {request} from '../api'
// Limit simultaneous decodes/downloads without retaining completed private blobs.
let running=0
const pending:Array<()=>void>=[]
function pump(){while(running<4&&pending.length)pending.shift()!()}
export function mediaRequest(path:string,signal:AbortSignal):Promise<Blob>{
 return new Promise((resolve,reject)=>{
  const abort=()=>{const i=pending.indexOf(start);if(i>=0){pending.splice(i,1);reject(new DOMException('Aborted','AbortError'))}}
  const start=()=>{signal.removeEventListener('abort',abort);if(signal.aborted){reject(new DOMException('Aborted','AbortError'));queueMicrotask(pump);return}running++;void request(path,{signal}).then(resolve,reject).finally(()=>{running--;pump()})}
  signal.addEventListener('abort',abort,{once:true});pending.push(start);pump()
 })
}
