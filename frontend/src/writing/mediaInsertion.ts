import {Marked} from 'marked'
import {serializeMedia,type MediaBlock} from './body'
const markdown=new Marked()
function columns(value:string){let size=0;for(const ch of value)size+=ch==='\t'?4-size%4:1;return size}
/** Insert at a collapsed source caret, preserving the surrounding list container.
 * No selected text is replaced. Literal code/HTML is rejected, never activated.
 */
export function sourceMediaInsertion(source:string,at:number,media:MediaBlock[]){
 if(!Number.isInteger(at)||at<0||at>source.length)throw new Error('原插入位置已失效，请重新选择正文位置')
 const tokens=markdown.lexer(source);let offset=0
 for(const token of tokens){const end=offset+token.raw.length;if(at>=offset&&at<end&&['code','html'].includes(token.type))throw new Error('不能在代码或HTML示例中插入私有图片，请选择正文位置');offset=end}
 const start=source.lastIndexOf('\n',Math.max(0,at-1))+1
 const before=source.slice(start,at),whole=source.slice(start).split('\n')[0]||''
 const bullet=/^([ \t]*)([-+*]|\d{1,9}[.)])([ \t]+)/.exec(whole)
 let indent=/^[ \t]*/.exec(before)?.[0]||''
 if(bullet&&at-start>=bullet[0].length){
  if(columns(bullet[0])-columns(bullet[1]+bullet[2])>4)throw new Error('列表标记后的缩进属于代码，请重新选择普通正文位置')
  indent=' '.repeat(columns(bullet[0]))
 }
 const empty=/^([ \t]*)([-+*]|\d{1,9}[.)])([ \t]*)$/.exec(before)
 const rest=source.slice(at,start+whole.length)
 if(empty&&!rest.trim()){
  const gap=empty[3]?'':' ',contentColumn=columns(before+gap)
  if(contentColumn-columns(empty[1]+empty[2])>4)throw new Error('列表标记后的缩进属于代码，请重新选择普通正文位置')
  const pad=' '.repeat(contentColumn),parts=media.map(serializeMedia)
  const first=parts[0]!.split('\n').map((line,index)=>index?pad+line:line).join('\n')
  const next=parts.slice(1).map(block=>block.split('\n').map(line=>pad+line).join('\n')).join('\n\n')
  let canonical='';for(const ch of before)canonical+=ch==='\t'?' '.repeat(4-canonical.length%4):ch
  const insertion=canonical+gap+first+(next?'\n\n'+next:'')+'\n\n'
  return {text:source.slice(0,start)+insertion+source.slice(at),caret:start+insertion.length}
 }
 const prefix='\n\n',payload=media.map(m=>serializeMedia(m).split('\n').map(line=>indent+line).join('\n')).join('\n\n')
 const insertion=prefix+payload+'\n\n'+(source[at]&&source[at]!=='\n'?indent:'')
 return {text:source.slice(0,at)+insertion+source.slice(at),caret:at+insertion.length}
}
