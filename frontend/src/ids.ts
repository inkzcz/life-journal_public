// randomUUID is unavailable on some NAS LAN origins. getRandomValues remains
// available there; never replace request identities with Math.random or time.
export function newId():string{
 const c=globalThis.crypto
 if(typeof c?.randomUUID==='function')return c.randomUUID()
 if(!c?.getRandomValues)throw new Error('浏览器不支持安全随机数，请使用支持的浏览器或私人 HTTPS 入口')
 const bytes=c.getRandomValues(new Uint8Array(16));bytes[6]=(bytes[6]!&15)|64;bytes[8]=(bytes[8]!&63)|128
 const hex=Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('')
 return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`
}
