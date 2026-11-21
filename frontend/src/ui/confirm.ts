import {shallowRef} from 'vue'
type Answer=boolean|string|null
type Pending={message:string;kind:'confirm'|'prompt';initial?:string;resolve:(value:Answer)=>void;focus:HTMLElement|null}
const queue:Pending[]=[]
export const confirmation=shallowRef<Pending|null>(null)
let hosts=0
export function attachConfirmHost(){hosts++;return ()=>{hosts--;cancelConfirmations()}}
function enqueue(kind:Pending['kind'],message:string,initial?:string):Promise<Answer>{return new Promise(resolve=>{queue.push({kind,message,initial,resolve,focus:document.activeElement instanceof HTMLElement?document.activeElement:null});if(!confirmation.value)confirmation.value=queue.shift()!})}
export async function confirmAction(message:string):Promise<boolean>{if(!hosts)return window.confirm(message);return (await enqueue('confirm',message))===true}
export async function promptAction(message:string,initial=''):Promise<string|null>{if(!hosts)return window.prompt(message,initial);const value=await enqueue('prompt',message,initial);return typeof value==='string'?value:null}
export function finishConfirmation(value:Answer){const active=confirmation.value;if(!active)return;confirmation.value=null;active.resolve(value);if(active.focus?.isConnected)active.focus.focus();if(queue.length)confirmation.value=queue.shift()!}
export function cancelConfirmations(){const current=confirmation.value;confirmation.value=null;current?.resolve(false);for(const item of queue.splice(0))item.resolve(false)}
