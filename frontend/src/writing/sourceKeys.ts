export function sourceEdit(text:string,start:number,end:number,key:string,shift=false,command=false,format=1){
 const before=text.slice(0,start),after=text.slice(end)
 if(command&&['b','i','`'].includes(key.toLowerCase())){const mark=key.toLowerCase()==='b'?'**':key==='`'?'`':'*';return {text:before+mark+text.slice(start,end)+mark+after,start:start+mark.length,end:end+mark.length}}
 if(key==='Tab'){
  // Treat versioned media metadata as an atomic block. Indenting only its JSON
  // line would break the container grammar although the JSON value is intact.
  if(format===2){
   const media=/^([ \t]*):::lj-media-v1\n[^\n]*\n\1:::(?:\n|$)/gm
   for(const block of text.matchAll(media))if(start<block.index!+block[0].length&&end>=block.index!)return {text,start,end}
  }

  const from=text.lastIndexOf('\n',start-1)+1,to=end>start&&text[end-1]==='\n'?end-1:end>start?end:start,part=text.slice(from,to)
  const lines=part.split('\n'),changed=lines.map(l=>shift?l.replace(/^( {1,2}|\t)/,''):'  '+l),delta=changed.join('\n').length-part.length
  return {text:text.slice(0,from)+changed.join('\n')+text.slice(to),start:Math.max(from,start+(changed[0].length-lines[0].length)),end:Math.max(from,end+delta)}
 }
 if(key==='Enter'&&start===end){const line=before.slice(before.lastIndexOf('\n')+1),m=/^(\s*)([-+*]|\d+[.)])\s+(\[[ xX]\]\s+)?(.*)$/.exec(line);if(!m)return
  if(!m[4].trim()){const at=before.length-line.length;return {text:text.slice(0,at)+m[1]+after,start:at+m[1].length,end:at+m[1].length}}
  const bullet=/^\d/.test(m[2])?String(parseInt(m[2])+1)+m[2].slice(-1):m[2],insert='\n'+m[1]+bullet+' '+(m[3]?'[ ] ':'');return {text:before+insert+after,start:start+insert.length,end:start+insert.length}
 }
}
