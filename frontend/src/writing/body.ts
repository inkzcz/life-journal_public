import {readEntry,entryMarker,type Entry} from './entries'
import { Marked,type TokensList } from 'marked'
export type MediaBlock={id:string;alt:string;caption:string;width:number;widthPercent?:number;layout?:'auto'|'single'|'grid';align:'left'|'center'|'right'}
export const marker=':::lj-media-v1'
export function mediaBlock(value:unknown):MediaBlock|null{
 const v=value as Partial<MediaBlock>
 if(!v||typeof v!=='object'||Object.keys(v).some(k=>!['id','alt','caption','width','widthPercent','align','layout'].includes(k))||! /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(v.id||''))return null
 if(v.alt!==undefined&&(typeof v.alt!=='string'||v.alt.length>1000)||v.caption!==undefined&&(typeof v.caption!=='string'||v.caption.length>2000))return null
 if(v.layout!==undefined&&!['auto','single','grid'].includes(v.layout))return null
 if(v.widthPercent!==undefined&&![30,60,100].includes(v.widthPercent))return null
 if(v.width!==undefined&&(!Number.isInteger(v.width)||v.width<120||v.width>1600)||v.align!==undefined&&!['left','center','right'].includes(v.align))return null
 return {id:v.id!,alt:v.alt||'',caption:v.caption||'',width:v.width||960,...(v.widthPercent?{widthPercent:v.widthPercent}:{}),...(v.layout?{layout:v.layout}:{}),align:v.align||'center'}
}
export function serializeMedia(v:MediaBlock){return `${marker}\n${JSON.stringify(v)}\n:::`}
export function readMedia(src:string){const match=/^:::lj-media-v1\n([^\n]*)\n:::(?:\n|$)/.exec(src);if(!match)return null;try{const attrs=mediaBlock(JSON.parse(match[1]!));return attrs?{raw:match[0],attrs}:null}catch{return null}}
const parser=new Marked({extensions:[{name:'lifeEntry',level:'block',start:s=>s.indexOf(entryMarker),tokenizer(src){const b=readEntry(src);if(b)return {type:'lifeEntry',raw:b.raw,attrs:b.attrs}}},{name:'privateMedia',level:'block',start:s=>s.indexOf(marker),tokenizer(src){const block=readMedia(src);if(block)return {type:'privateMedia',raw:block.raw,attrs:block.attrs}}}]})
export type BodyPart={source:string;raw?:string;media?:MediaBlock}
export function bodyParts(source:string,format=1):BodyPart[]{
 if(format!==2)return [{source}]
 const parts:BodyPart[]=[];let text=''
 for(const t of parser.lexer(source)){if(t.type==='privateMedia'){if(text)parts.push({source:text});text='';parts.push({source:'',raw:t.raw,media:t.attrs})}else text+=t.raw}
 if(text||!parts.length)parts.push({source:text});return parts
}
// Do not silently coerce unsupported Markdown/HTML into a smaller editor schema.
export function visualCompatible(source:string){
 const tokens=parser.lexer(source)
 const supported=new Set(['space','heading','paragraph','text','strong','em','codespan','code','blockquote','list','list_item','link','br','hr','escape','privateMedia','lifeEntry','def'])
 function check(items:any[]):boolean{return items.every(t=>supported.has(t.type)&&!t.task&&(!t.tokens||check(t.tokens))&&(!t.items||check(t.items)))}
 function malformed(items:any[]):boolean{return items.some(t=>t.type==='code'||t.type==='privateMedia'||t.type==='lifeEntry'?false:t.type==='list'?t.items.some((i:any)=>malformed(i.tokens||[])):t.type==='blockquote'?/:::lj-(?:media|entry)-v\d/.test(t.raw||'')||malformed(t.tokens||[]):/:::lj-(?:media|entry)-v\d/.test(t.raw||''))}
 return check(tokens)&&!malformed(tokens)
}

export function mediaStyle(v:MediaBlock){return {width:v.widthPercent?v.widthPercent+'%':'100%',maxWidth:v.widthPercent?'100%':v.width+'px',marginLeft:v.align==='left'?'0':'auto',marginRight:v.align==='right'?'0':'auto'}}

// Keep container structure when rendering private media inside list items.
// Code samples and blockquotes retain their historical, inert interpretation.
export type BodyNode={entry?:Entry;gallery?:MediaBlock[];source?:string;media?:MediaBlock;tag?:'ul'|'ol'|'li';start?:number;children?:BodyNode[]}
export type BodyTree=BodyNode[]&{links?:TokensList['links']}
export function bodyTree(source:string,format=1):BodyTree{
 if(format!==2)return [{source}]
 function nodes(tokens:any[]):BodyNode[]{
  const result:BodyNode[]=[];let source=''
  const flush=()=>{if(source){result.push({source});source=''}}
  for(const t of tokens){
   if(t.type==='lifeEntry'){flush();result.push({entry:t.attrs})}
   else if(t.type==='privateMedia'){flush();result.push({media:t.attrs})}
   else if(t.type==='list'){flush();result.push({tag:t.ordered?'ol':'ul',start:t.ordered?t.start:undefined,children:t.items.map((item:any)=>({tag:'li',children:nodes(item.tokens)}))})}
   else source+=t.raw
  }
  flush();return result
 }
 const tokens=parser.lexer(source)
 return Object.assign(nodes(tokens),{links:tokens.links})
}
export function bodyMedia(source:string,format=1):MediaBlock[]{
 function collect(nodes:BodyNode[]):MediaBlock[]{return nodes.flatMap(n=>n.media?[n.media]:n.children?collect(n.children):[])}
 return collect(bodyTree(source,format))
}


export function compactEligible(m:MediaBlock){return m.layout==='grid'||m.layout!=='single'&&!m.widthPercent&&m.width===960&&m.align==='center'}
export function compactBody(nodes:BodyNode[]):BodyNode[]{
 const result:BodyNode[]=[]
 for(let i=0;i<nodes.length;i++){
  const node=nodes[i]!
  if(node.children){result.push({...node,children:compactBody(node.children)});continue}
  if(!node.media||!compactEligible(node.media)){result.push(node);continue}
  const images=[node.media];let end=i,j=i+1
  while(j<nodes.length){const next=nodes[j]!;if(next.source!==undefined&&!next.source.trim()){j++;continue}if(next.media&&compactEligible(next.media)){images.push(next.media);end=j;j++;continue}break}
  if(images.length>1){result.push({gallery:images});i=end}else result.push(node)
 }
 return result
}
