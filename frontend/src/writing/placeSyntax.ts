// Mirrors services/markdown_marks.py. Do not guess where a Chinese name ends.
export function placeToken(source:string){
 const match=/^@([lfshtcp])(?:\[([^\]\n\x00]+)\]|([^\S\n]+[^\n@\x00]+)|([^\s@\[\]{}\x00]+))(?:[ \t]*\{#place:[^}\n]*\})?/.exec(source)
 if(!match)return null
 const name=(match[2]??match[3]??match[4]??'').replace(/\s*\{#place:[0-9a-f-]{36}\}\s*$/,'').trim()
 if(!name||name.length>200||name.includes('{#place:'))return null
 return {raw:match[0],kind:match[1]!,name}
}
export function placeStart(source:string){
 const regex=/(?:(?<![\p{L}\p{N}_@])|(?<=[\u3400-\u9fff]))@[lfshtcp](?=\[|\s|[^\s@\[\]{}])/gu
 for(const match of source.matchAll(regex)){
  if(!/\S*(?:https?:\/\/|www\.|mailto:)\S*$/i.test(source.slice(0,match.index)))return match.index!
 }
 return -1
}
