import {Marked} from 'marked'
import {serializeEntry,type Entry} from './entries'
const markdown=new Marked()
function columns(value:string){let size=0;for(const ch of value)size+=ch==='\t'?4-size%4:1;return size}
/** Build one atomic source edit without changing either adjacent text segment. */
export function sourceEntryInsertion(source:string,at:number,commandLength:number,entry:Entry){
 const from=at-commandLength
 if(!Number.isInteger(at)||from<0||at>source.length)throw Error('原插入位置已失效，请重新选择正文位置')
 let offset=0
 for(const token of markdown.lexer(source)){const end=offset+token.raw.length;if(from>=offset&&from<end&&['code','html','table'].includes(token.type))throw Error('请在代码、HTML 或表格之外选择正文位置');offset=end}
 // Private blocks are atomic. Never splice a card into their JSON or delimiters.
 for(const block of source.matchAll(/^([ \t]*):::lj-(?:media|entry)-v\d+\r?\n[\s\S]*?^\1:::(?:\r?\n|$)/gm))if(from>=block.index!&&from<block.index!+block[0].length)throw Error('请在已有卡片或图片元数据之外选择正文位置')
 const start=source.lastIndexOf('\n',Math.max(0,from-1))+1,line=source.slice(start).split('\n')[0]||'',before=source.slice(start,from)
 const bullet=/^([ \t]*)([-+*]|\d{1,9}[.)])([ \t]+)/.exec(line)
 let indent=/^[ \t]*/.exec(before)?.[0]||''
 if(bullet&&from-start>=bullet[0].length){if(columns(bullet[0])-columns(bullet[1]+bullet[2])>4)throw Error('请在代码缩进之外选择正文位置');indent=' '.repeat(columns(bullet[0]))}
 const empty=/^([ \t]*)([-+*]|\d{1,9}[.)])([ \t]*)$/.exec(before),block=serializeEntry(entry)
 if(empty&&!source.slice(at,start+line.length).trim()){
  const gap=empty[3]?'':' ',pad=' '.repeat(columns(before+gap)),text=gap+block.split('\n').map((part,i)=>i?pad+part:part).join('\n')+'\n\n'
  return {from,to:at,text,value:source.slice(0,from)+text+source.slice(at),caret:from+text.length}
 }
 const text='\n\n'+block.split('\n').map(part=>indent+part).join('\n')+'\n\n'+(source[at]&&source[at]!=='\n'?indent:'')
 return {from,to:at,text,value:source.slice(0,from)+text+source.slice(at),caret:from+text.length}
}
