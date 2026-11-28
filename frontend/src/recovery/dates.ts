/** Display only: never mutate stored UTC instants or accept raw HTML. */
export function formatRecoveryTime(value:string,timezone:string):string{
 const date=new Date(value)
 if(!Number.isFinite(date.getTime()))return '时间未知'
 try{return new Intl.DateTimeFormat('zh-CN',{timeZone:timezone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(date)}catch{return new Intl.DateTimeFormat('zh-CN',{timeZone:'UTC',dateStyle:'short',timeStyle:'medium',hour12:false}).format(date)+' UTC'}
}
