import {newId} from '../ids'
import {Plugin} from '@tiptap/pm/state'
import {Slice,Fragment,type Node as PMNode} from '@tiptap/pm/model'
import { Node } from '@tiptap/core'
import { VueNodeViewRenderer } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import {ListItem,OrderedList} from '@tiptap/extension-list'
import { Markdown } from '@tiptap/markdown'
import EntryNode from './EntryNode.vue'
import {readEntry,serializeEntry,validEntry} from './entries'
import PrivateMediaNode from './PrivateMediaNode.vue'
import {readMedia,serializeMedia,mediaBlock} from './body'
export const PrivateMedia=Node.create({
 name:'privateMedia',group:'block',atom:true,draggable:true,
 addAttributes(){return {id:{default:''},alt:{default:''},caption:{default:''},width:{default:960},widthPercent:{default:null},align:{default:'center'},layout:{default:null}}},
 // Never parse arbitrary pasted HTML as a trusted media node.
 parseHTML(){return []},renderHTML(){return ['div',{'data-private-media':'true'},'私有图片']},
 addNodeView(){return VueNodeViewRenderer(PrivateMediaNode)},
 markdownTokenizer:{name:'privateMedia',level:'block',start:s=>s.indexOf(':::lj-media-v1'),tokenize(src){const b=readMedia(src);if(b)return {type:'privateMedia',raw:b.raw,attrs:b.attrs}}},
 parseMarkdown:(token,h)=>h.createNode('privateMedia',token.attrs),
 renderMarkdown:node=>{const b=mediaBlock(Object.fromEntries(Object.entries(node.attrs||{}).filter(([,v])=>v!==null)));return b?serializeMedia(b):''},
})
export const LifeEntry=Node.create({
 name:'lifeEntry',group:'block',atom:true,draggable:true,
 addProseMirrorPlugins(){
  const copy=(slice:Slice)=>{const remap=(node:PMNode):PMNode=>node.type.name==='lifeEntry'?node.type.create({...node.attrs,value:{...node.attrs.value,id:newId()}}):node.copy(Fragment.fromArray(Array.from({length:node.childCount},(_,i)=>remap(node.child(i)))));return new Slice(Fragment.fromArray(Array.from({length:slice.content.childCount},(_,i)=>remap(slice.content.child(i)))),slice.openStart,slice.openEnd)}
  const contains=(slice:Slice)=>{let found=false;slice.content.descendants(n=>{if(n.type.name==='lifeEntry')found=true});return found}
  return [new Plugin({props:{
   handlePaste(view,_event,slice){if(!contains(slice))return false;view.dispatch(view.state.tr.replaceSelection(copy(slice)).scrollIntoView());return true},
   handleDrop(view,event,slice,moved){if(moved||!contains(slice))return false;const at=view.posAtCoords({left:event.clientX,top:event.clientY});if(!at)return true;view.dispatch(view.state.tr.replaceRange(at.pos,at.pos,copy(slice)).scrollIntoView());return true},
  }})]
 },
 addAttributes(){return {value:{default:null}}},
 parseHTML(){return [{tag:'div[data-life-entry-v1]',getAttrs:el=>{try{const raw=(el as HTMLElement).getAttribute('data-life-entry-v1')||'';if(raw.length>300000)return false;const value=JSON.parse(raw);return validEntry(value)?{value}:false}catch{return false}}}]},
 renderHTML({node}){return ['div',{'data-life-entry-v1':JSON.stringify(node.attrs.value)},'@'+node.attrs.value.kind+' '+node.attrs.value.name]},
 addNodeView(){return VueNodeViewRenderer(EntryNode)},
 markdownTokenizer:{name:'lifeEntry',level:'block',start:s=>s.indexOf(':::lj-entry-v1'),tokenize(src){const b=readEntry(src);if(b)return {type:'lifeEntry',raw:b.raw,attrs:{value:b.attrs}}}},
 parseMarkdown:(token,h)=>h.createNode('lifeEntry',token.attrs),renderMarkdown:node=>serializeEntry(node.attrs!.value),
})
// ProseMirror requires a leading paragraph in a list item, even when its only
// authored content is an image. Serializing that empty schema placeholder as
// "- \n  :::" is ambiguous CommonMark (and may become a setext heading).
// Keep the placeholder in editor state, but put the image on the marker line.
export const WritingListItem=ListItem.extend({
 renderMarkdown(node,h,ctx){
  const children=node.content||[]
  const placeholder=children[0]?.type==='paragraph'&&!children[0].content?.length&&['privateMedia','lifeEntry'].includes(children[1]?.type||'')
  const normalized=placeholder?{...node,content:children.slice(1)}:node
  if(!['privateMedia','lifeEntry'].includes(normalized.content?.[0]?.type||''))return this.parent?.(normalized,h,ctx)||''
  // The upstream list renderer prefixes only the FIRST line of its main
  // block. A private block is multiline; indent its JSON and closing marker
  // to the content column too, including multi-digit ordered-list prefixes.
  const prefix=this.parent?.({...node,content:[{type:'paragraph'}]},h,ctx)||'- '
  let first=true
  return this.parent?.(normalized,{...h,renderChildren(nodes,separator){
   const value=h.renderChildren(nodes,separator)
   if(!first)return value
   first=false;return value.split('\n').map((line,index)=>index?' '.repeat(prefix.length)+line:line).join('\n')
  }},ctx)||''
 },
 parseMarkdown(token,h){
  const parsed=this.parent?.(token,h)
  const normalize=(item:any)=>item?.type==='listItem'&&['privateMedia','lifeEntry'].includes(item.content?.[0]?.type||'')?{...item,content:[{type:'paragraph'},...item.content]}:item
  return Array.isArray(parsed)?parsed.map(normalize):normalize(parsed)
 },
})
// The optional roman-list tokenizer in this TipTap version under-dedents
// multiline private blocks in numeric list items. Use Marked's CommonMark list
// tokenizer for those documents, matching our reader, instead of relaxing media.
const orderedTokenizer=OrderedList.config.markdownTokenizer
export const WritingOrderedList=OrderedList.extend({
 parseMarkdown(token,h){
  const parsed=this.parent?.(token,h)
  // OrderedList parses children directly, bypassing ListItem's parser.
  const normalize=(node:any):any=>{
   if(!node||typeof node!=='object')return node
   const content=node.content?.map(normalize)
   return {...node,...(content?{content:node.type==='listItem'&&['privateMedia','lifeEntry'].includes(content[0]?.type||'')?[{type:'paragraph'},...content]:content}:{})}
  }
  return Array.isArray(parsed)?parsed.map(normalize):normalize(parsed)
 },
 markdownTokenizer:{name:'orderedList',level:'block',start:()=>-1,tokenize(src,tokens,lexer){
  if(/^[ \t]*\d{1,9}[.)][ \t]+/.test(src)&&/:::lj-(?:media|entry)-v1/.test(src))return undefined
  return orderedTokenizer?.tokenize(src,tokens,lexer)
 }},
})
export const writingExtensions=()=>[StarterKit.configure({listItem:false,orderedList:false,link:{openOnClick:false,protocols:['http','https','mailto'],autolink:false},underline:false}),WritingListItem,WritingOrderedList,PrivateMedia,LifeEntry,Markdown]
