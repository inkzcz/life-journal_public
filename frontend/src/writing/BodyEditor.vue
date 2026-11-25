<script setup lang="ts">
import {confirmAction,promptAction} from '../ui/confirm'
import {marked} from 'marked'
import {textareaCaret,suggestionMatch,type Caret} from './caret'
import {indentVisualText} from './visualKeys'
import {sourceEdit} from './sourceKeys'
import {sourceMediaInsertion} from './mediaInsertion'
import EntryForm from './EntryForm.vue'
import EntryCard from './EntryCard.vue'
import EntryCardActions from './cards/EntryCardActions.vue'
import {entryTransferKey} from './entryTransfer'
import {blankEntry,serializeEntry,validEntry,entryLocations,sourceCardChange,type Entry,type EntryKind} from './entries'
import {newId} from '../ids'
import { inject,ref,reactive,markRaw,watch,computed,onMounted,onBeforeUnmount } from 'vue'
import { useEditor,EditorContent } from '@tiptap/vue-3'
import type { SelectionBookmark } from '@tiptap/pm/state'
import { TextSelection } from '@tiptap/pm/state'
import {closeHistory} from '@tiptap/pm/history'
import {sourcePatch,type AICapture,type AIApply} from '../exchange/selection'
import { request,uploadImage } from '../api'
import type { Asset } from '../admin/archive'
import FolderSelect from '../admin/FolderSelect.vue'
import PrivatePreview from '../admin/PrivatePreview.vue'
import PlaceSuggest from './PlaceSuggest.vue'
import EditorTools from './EditorTools.vue'
import { writingExtensions } from './extensions'
import { visualCompatible,serializeMedia,bodyParts,type MediaBlock } from './body'
const props=withDefaults(defineProps<{modelValue:string;recordId?:string;folderId?:string;title?:string;disabled?:boolean;format?:number}>(),{format:1})
const emit=defineEmits<{(e:'update:modelValue',value:string):void;(e:'update:format',value:number):void;(e:'pending',value:boolean):void;(e:'uploaded',id:string):void}>()
const suggest=ref<{key:(e:KeyboardEvent)=>boolean}|null>(null),context=ref('')
const composing=ref(false),anchor=ref<Caret>(),sourceBuffer=ref(props.modelValue)
let compositionFrame=0,externalDuringComposition=false
const entryTimeValid=ref(true)
const entryDraft=ref<Entry>(),entryDialog=ref<HTMLDialogElement>(),entryError=ref('')
const transfer=inject(entryTransferKey,undefined)
async function sourceAction(card:{at:number;raw:string;entry:Entry},action:string){if(props.disabled||composing.value)return;if(action==='edit'){editSourceEntry(card);return}if(action==='copy'||action==='move'){await transfer?.(card.entry,action);return}if(action==='delete'&&!await confirmAction('仅删除此卡片？关联媒体和历史保留。'))return;if(['duplicate','delete','up','down'].includes(action)){publish(sourceCardChange(sourceBuffer.value,card.entry.id,action as 'duplicate'|'delete'|'up'|'down'))}}
const sourceCards=computed(()=>entryLocations(sourceBuffer.value))
let editingSource:{at:number;raw:string}|undefined
function editSourceEntry(card:{at:number;raw:string;entry:Entry}){editingSource={at:card.at,raw:card.raw};entryDraft.value=JSON.parse(JSON.stringify(card.entry));entryError.value='';queueMicrotask(()=>entryDialog.value?.showModal())}
let entryAt:number|undefined,entryBookmark:SelectionBookmark|undefined
function openEntry(){if(composing.value)return;editingSource=undefined;entryDraft.value=blankEntry();entryAt=source.value?.selectionStart;entryBookmark=editor.value?markRaw(editor.value.state.selection.getBookmark()):undefined;entryError.value='';queueMicrotask(()=>entryDialog.value?.showModal())}
function addEntry(){if(!entryTimeValid.value){entryError.value='请先处理时间与时区提示';return}const v=entryDraft.value;if(!v||!validEntry(v)){entryError.value='请填写名称';return}emit('update:format',2);if(editingSource){const old=editingSource;if(sourceBuffer.value.slice(old.at,old.at+old.raw.length)!==old.raw){entryError.value='正文已变化，请取消后重新打开卡片';return}publish(sourceBuffer.value.slice(0,old.at)+serializeEntry(v)+(old.raw.endsWith('\n')?'\n':'')+sourceBuffer.value.slice(old.at+old.raw.length));editingSource=undefined;entryDialog.value?.close();return}if(mode.value==='visual'&&editor.value){let at:number;try{at=entryBookmark!.resolve(editor.value.state.doc).from}catch{entryError.value='位置失效，请关闭表单并重新指定正文位置';return}editor.value.chain().setTextSelection(at).insertContent({type:'lifeEntry',attrs:{value:JSON.parse(JSON.stringify(v))}}).run()}else{if(entryAt===undefined||entryAt<0||entryAt>sourceBuffer.value.length){entryError.value='位置失效，请重新指定正文位置';return}publish(sourceBuffer.value.slice(0,entryAt)+'\n\n'+serializeEntry(v)+'\n\n'+sourceBuffer.value.slice(entryAt))}entryDialog.value?.close()}
const toolsTab=ref<'media'|'ai'>('media'),aiMounted=ref(false)
let pickerBookmark:SelectionBookmark|undefined,pickerAt:number|undefined
const toolbar=ref<HTMLElement|null>(null),toolbarTop=ref(0),toolsTop=ref(0)
let stickyObserver:ResizeObserver|undefined
function stickyOffset(){const root=toolbar.value?.closest('.writing-page,.studio')||document;let bottom=0;const bars=Array.from(root.querySelectorAll<HTMLElement>('.workspace-save,.blog-header,.writing-header,.studio-header')).filter(el=>['fixed','sticky'].includes(getComputedStyle(el).position)).map(el=>el.getBoundingClientRect()).sort((a,b)=>a.top-b.top);for(const r of bars)if(r.height&&r.top<=bottom+1&&r.bottom>bottom)bottom=r.bottom;toolbarTop.value=Math.max(0,bottom);const critical=Array.from(root.querySelectorAll<HTMLElement>('.workspace-save,.writing-header,.blog-header')).map(el=>el.getBoundingClientRect()).filter(r=>r.height&&r.top<window.innerHeight&&r.bottom>0);toolsTop.value=Math.max(0,...critical.map(r=>r.bottom))}
function composition(value:boolean){
 if(value){if(compositionFrame){cancelAnimationFrame(compositionFrame);compositionFrame=0}composing.value=true;pending();return}
 if(!composing.value||compositionFrame)return
 // Browser input/ProseMirror can commit the final character after compositionend.
 compositionFrame=requestAnimationFrame(()=>{compositionFrame=0;if(!alive)return
  if(mode.value==='source'&&source.value)publish(source.value.value)
  else if(editor.value)publish(editor.value.getMarkdown())
  composing.value=false
  if(externalDuringComposition){message.value='输入期间收到外部同步，已保留当前输入；请核对保存状态。';externalDuringComposition=false}
  for(const j of jobs.value)if(j.status==='waiting'&&j.asset){insert(j.asset,j.bookmark,j.sourceAt);j.status='done';j.file=undefined}
  pending();updateCaret()
 })
}
const mode=ref<'visual'|'source'>(visualCompatible(props.modelValue)&&(props.format===2||!/:::lj-(?:media|entry)-v1/.test(props.modelValue))?'visual':'source'),message=ref(''),fileInput=ref<HTMLInputElement|null>(null),source=ref<HTMLTextAreaElement|null>(null)
type Job={key:string;file?:File;status:'uploading'|'error'|'done'|'waiting';message:string;progress?:number;sourceAt?:number;bookmark?:SelectionBookmark;asset?:Asset;folderId?:string;adoptIntoArticle?:boolean;autoArchive?:boolean}
const uploadFolder=ref(props.folderId||''),folderGeneration=ref(0),folderExplicit=ref(false)
function articleFolder(){folderExplicit.value=false;if(props.folderId){uploadFolder.value=props.folderId;message.value='已选择文章稳定绑定的专属文件夹；文章改名不会改变绑定'}else message.value='请先成功保存文章或草稿；专属文件夹会在同一事务中创建，不重复创建目录。'}
watch(()=>props.folderId,id=>{if(!folderExplicit.value&&!uploadFolder.value)uploadFolder.value=id||'';folderGeneration.value++})
const folder=ref('*'),chosen=ref<Asset[]>([]),largePreview=ref<Asset|null>(null)
const jobs=ref<Job[]>([]),picker=ref(false),assets=ref<Asset[]>([]),q=ref(''),page=ref(1),total=ref(0),searching=ref(false)
const documentRevision=ref(0)
let alive=true,importing=false,writing=false,lastPublished:string|undefined;const controllers=new Set<AbortController>()
watch(source,el=>{if(el)el.value=sourceBuffer.value},{flush:'post'})
function publish(value:string){const old=sourceBuffer.value;if(value!==old)documentRevision.value++;sourceBuffer.value=value;if(source.value&&!composing.value&&source.value.value!==value)source.value.value=value;let start=0,end=old.length,nextEnd=value.length;while(start<end&&start<nextEnd&&old[start]===value[start])start++;while(end>start&&nextEnd>start&&old[end-1]===value[nextEnd-1]){end--;nextEnd--}for(const j of jobs.value)if(j.sourceAt!==undefined&&j.sourceAt>start)j.sourceAt=j.sourceAt>=end?j.sourceAt+nextEnd-end:nextEnd;if(pickerAt!==undefined&&pickerAt>start)pickerAt=pickerAt>=end?pickerAt+nextEnd-end:nextEnd;lastPublished=value;writing=true;emit('update:modelValue',value);queueMicrotask(()=>writing=false)}
const editor=useEditor({extensions:writingExtensions(),content:visualCompatible(props.modelValue)?props.modelValue:'',contentType:'markdown',editable:!props.disabled,
 editorProps:{handleKeyDown:(_view,event)=>visualKey(event),handleDOMEvents:{compositionstart:()=>{composition(true);return false},compositionend:()=>{composition(false);return false}},attributes:{class:'immersive-prose', 'aria-label':'可视化文章正文',role:'textbox','aria-multiline':'true'},handlePaste:(_view,event)=>{const files=Array.from(event.clipboardData?.files||[]);if(files.length){event.preventDefault();void upload(files);return true}return false},handleDrop:(view,event,_slice,moved)=>{if(moved)return false;const files=Array.from(event.dataTransfer?.files||[]);if(!files.length)return false;event.preventDefault();const at=view.posAtCoords({left:event.clientX,top:event.clientY});if(at)view.dispatch(view.state.tr.setSelection(TextSelection.near(view.state.doc.resolve(at.pos))));void upload(files);return true}},
 onBlur:()=>{context.value=''},
 onSelectionUpdate:({editor:e})=>{if(picker.value&&e.isFocused)pickerBookmark=markRaw(e.state.selection.getBookmark());queueMicrotask(updateCaret);if(!e.state.selection.empty||e.isActive('codeBlock')||e.isActive('code')){context.value='';return}const p=e.state.selection.$from;context.value=e.state.doc.textBetween(p.start(),p.pos,'\n')},
 onTransaction:({transaction})=>{if(transaction.docChanged)documentRevision.value++;if(pickerBookmark)pickerBookmark=markRaw(pickerBookmark.map(transaction.mapping));for(const j of jobs.value)if(j.bookmark)j.bookmark=markRaw(j.bookmark.map(transaction.mapping))},
 onUpdate:({editor:e,transaction})=>{if(importing||composing.value||mode.value!=='visual'||!transaction.docChanged)return;const p=e.state.selection.$from;context.value=e.state.doc.textBetween(p.start(),p.pos,'\n');const value=e.getMarkdown();if(value.length>300000){message.value='正文超过300000字符，请缩短后保存'}publish(value)},
})
watch(()=>props.disabled,value=>editor.value?.setEditable(!value,false))
watch(()=>props.modelValue,value=>{if(composing.value){if(value!==lastPublished)externalDuringComposition=true;return}if(sourceBuffer.value!==value){documentRevision.value++;if(!writing&&value!==lastPublished){pickerBookmark=undefined;pickerAt=undefined;if(picker.value)message.value='正文已被外部更新，请重新指定图片插入位置'}}sourceBuffer.value=value;if(source.value&&mode.value==='source'&&source.value.value!==value)source.value.value=value;if(writing||value===lastPublished||!editor.value)return;if(mode.value==='visual'&&!visualCompatible(value)){mode.value='source';message.value='包含当前可视化模式不支持的语法，已保留源码。'}else if(mode.value==='visual'&&editor.value.getMarkdown()!==value){importing=true;editor.value.commands.setContent(value,{contentType:'markdown',emitUpdate:false});importing=false}})
function switchMode(){if(composing.value||jobs.value.some(j=>j.status!=='done')){message.value='请先完成或取消上传，再切换模式';return}if(mode.value==='source'){if(!visualCompatible(props.modelValue)||props.format!==2&&/:::lj-(?:media|entry)-v1/.test(props.modelValue)){message.value='当前文档含可视化编辑器尚不支持的语法（例如表格、HTML、普通图片或扩展块）。已保留全部源码；仍可在源码中上传、粘贴和拖入图片。';return}importing=true;editor.value?.commands.setContent(props.modelValue,{contentType:'markdown',emitUpdate:false});importing=false;mode.value='visual'}else mode.value='source';pickerBookmark=undefined;pickerAt=undefined;if(picker.value)message.value='编辑模式已切换，请重新指定图片插入位置';else message.value=''}
const sourceImages=computed(()=>bodyParts(props.modelValue,props.format).map((p,index)=>({...p,index})).filter(p=>p.media))
function changeSourceImage(index:number,patch:Partial<MediaBlock>){const parts=bodyParts(props.modelValue,props.format);const part=parts[index];if(!part?.media)return;const attrs={...part.media,...patch};if(!attrs.widthPercent)delete attrs.widthPercent;publish(parts.map((p,i)=>i===index?serializeMedia(attrs)+(p.raw?.endsWith('\n')?'\n':''):p.media?p.raw||serializeMedia(p.media):p.source).join(''))}
function insert(asset:Asset,bookmark?:SelectionBookmark,sourceAt?:number){insertAssets([asset],bookmark,sourceAt)}
function insertAssets(selected:Asset[],bookmark?:SelectionBookmark,sourceAt?:number){
 if(props.disabled||composing.value||!selected.length)return false

 const shouldFocus=(!bookmark&&sourceAt===undefined)||editor.value?.isFocused||document.activeElement===source.value
 // Publish the format before the body: synchronous consumers must never see
 // a versioned media block paired with legacy format 1.
 emit('update:format',2)
 const attrs:MediaBlock[]=selected.map(asset=>({id:asset.id,alt:asset.alt||asset.filename,caption:'',width:960,align:'center'}))
 if(mode.value==='visual'&&editor.value){const e=editor.value;let chain=e.chain();if(shouldFocus)chain=chain.focus(undefined,{scrollIntoView:false});if(bookmark){try{chain=chain.setTextSelection(bookmark.resolve(e.state.doc).from)}catch{message.value='原插入位置已失效，请在正文重新指定插入位置；图片仍保留在媒体库。';return false}}if(!chain.insertContent(attrs.map(value=>({type:'privateMedia',attrs:value}))).run()){message.value='当前位置无法插入图片，请重新选择正文位置；原文与媒体保留。';return false}}
 else {const at=sourceAt??source.value?.selectionStart??-1,scroll=window.scrollY
  try{const change=sourceMediaInsertion(sourceBuffer.value,at,attrs);publish(change.text);if(picker.value&&toolsTab.value==='media')pickerAt=change.caret;queueMicrotask(()=>{if(shouldFocus)source.value?.focus({preventScroll:true});source.value?.setSelectionRange(change.caret,change.caret);window.scrollTo({top:scroll})})}
  catch(e){message.value=String(e)+'；已上传图片仍保存在私有媒体库中。';return false}
 }

 message.value='图片已加入本页草稿，文章保存后关联；移除图片不会删除原图。'
 return true
}
function pending(){emit('pending',composing.value||jobs.value.some(j=>j.status==='uploading'||j.status==='error'||j.status==='waiting'))}
async function send(job:Job){
 if(!job.file||!alive)return;job.status='uploading';pending();const controller=new AbortController();controllers.add(controller);const timeout=setTimeout(()=>controller.abort(),120000)
 try{const form=new FormData();form.append('file',job.file);form.append('auto_archive',job.autoArchive===false?'false':'true');if(job.folderId)form.append('folder_id',job.folderId);const asset=await uploadImage('/admin/archive/media',form,job.key,controller.signal,value=>job.progress=value) as Asset;if(!alive)return;job.asset=asset;if(job.adoptIntoArticle)emit('uploaded',asset.id);if(composing.value){job.status='waiting'}else{insert(asset,job.bookmark,job.sourceAt);job.status='done';job.file=undefined}}
 catch(e){if(alive){job.status='error';job.message=(e as Error).name==='AbortError'?'上传超时，结果尚未确认；重试会使用相同请求标识核对。':String(e)}}finally{clearTimeout(timeout);controllers.delete(controller);if(alive)pending()}
}
async function upload(files:File[]){if(props.disabled)return;if(composing.value){message.value='请先确认正在输入的文字，再插入图片';return}for(const file of files){if(!alive)break;let key:string;try{key=newId()}catch(e){message.value=String(e);return}const job:Job=reactive({key,file,folderId:uploadFolder.value,autoArchive:!folderExplicit.value,adoptIntoArticle:!folderExplicit.value&&!uploadFolder.value,status:'uploading',message:'',sourceAt:mode.value==='source'?source.value?.selectionStart:undefined,bookmark:editor.value?markRaw(editor.value.state.selection.getBookmark()):undefined});jobs.value.push(job);if(file.type&&!['image/jpeg','image/png','image/webp'].includes(file.type)||file.size>10*1024*1024){job.status='error';job.message='请选择10MB以内的JPG、PNG或WebP图片';pending();continue}await send(job)}}
function updateCaret(){if(composing.value)return;if(mode.value==='source'&&source.value){if(picker.value&&document.activeElement===source.value)pickerAt=source.value.selectionStart;sourceContext();anchor.value=context.value?textareaCaret(source.value):undefined}else if(editor.value&&!editor.value.isDestroyed){try{const e=editor.value;if(!e.isFocused||!e.state.selection.empty||e.isActive('code')||e.isActive('codeBlock')){context.value='';return}const at=e.state.selection.$from;context.value=e.state.doc.textBetween(at.start(),at.pos,'\n');const r=editor.value.view.coordsAtPos(editor.value.state.selection.from);anchor.value={left:r.left,top:r.top,bottom:r.bottom}}catch{/* selection may be detached during mode changes */}}}
onMounted(()=>{window.addEventListener('scroll',stickyOffset,true);window.addEventListener('resize',stickyOffset);if(typeof ResizeObserver!=='undefined'){stickyObserver=new ResizeObserver(stickyOffset);const root=toolbar.value?.closest('.writing-page,.studio')||document;root.querySelectorAll('.workspace-save,.blog-header,.writing-header,.studio-header').forEach(el=>stickyObserver?.observe(el))}stickyOffset();window.addEventListener('scroll',updateCaret,true);window.addEventListener('resize',updateCaret);window.visualViewport?.addEventListener('resize',updateCaret);window.visualViewport?.addEventListener('scroll',updateCaret)})
watch(context,()=>queueMicrotask(updateCaret))
function sourceContext(){const el=source.value;if(!el||document.activeElement!==el){context.value='';anchor.value=undefined;return}
 const before=el.value.slice(0,el.selectionStart),line=before.split('\n').at(-1)||''
 if(el.selectionStart!==el.selectionEnd||!suggestionMatch(line)){context.value='';return}
 let tokens:any[]=marked.lexer(before),last:any=tokens.at(-1)
 while(last?.items||last?.tokens){tokens=last.items?last.items.at(-1).tokens:last.tokens;last=tokens.at(-1)}
 context.value=el.selectionStart!==el.selectionEnd||last?.type==='code'?'':before.split('\n').at(-1)||''
}
let releaseTab=false
function visualKey(event:KeyboardEvent){
 if(composing.value||event.isComposing||props.disabled)return false
 if(suggest.value?.key(event))return true
 if(event.key==='Escape'){releaseTab=true;return false}
 if(event.key!=='Tab'){releaseTab=false;return false}
 if(releaseTab){releaseTab=false;return false}
 const e=editor.value;if(!e)return false
 event.preventDefault()
 if(e.isActive('listItem')){if(event.shiftKey)e.commands.liftListItem('listItem');else e.commands.sinkListItem('listItem')}
 else indentVisualText(e.view,event.shiftKey)
 return true
}
function sourceKey(e:KeyboardEvent){if(composing.value||e.isComposing||props.disabled)return;if((e.ctrlKey||e.metaKey)&&!e.shiftKey&&e.key.toLowerCase()==='z'&&canUndoAI.value){e.preventDefault();undoAI();return;}if(suggest.value?.key(e))return;if(e.key==='Escape'){releaseTab=true;return}if(e.key==='Tab'&&releaseTab){releaseTab=false;return}releaseTab=false;const el=source.value;if(!el)return;const change=sourceEdit(sourceBuffer.value,el.selectionStart,el.selectionEnd,e.key,e.shiftKey,e.ctrlKey||e.metaKey,props.format);if(!change)return;e.preventDefault();const scroll=el.scrollTop;publish(change.text);queueMicrotask(()=>{el.setSelectionRange(change.start,change.end);el.scrollTop=scroll;sourceContext()})}
function sourceInput(e:Event){if(composing.value)return;const el=e.target as HTMLTextAreaElement;publish(el.value);sourceContext()}
function chooseEntry(v:{length:number;context:string;kind:EntryKind}){if(context.value!==v.context)return;choosePlace({...v,text:''});queueMicrotask(()=>{openEntry();if(entryDraft.value)entryDraft.value.kind=v.kind})}
function choosePlace(v:{length:number;text:string;context:string}){if(composing.value||props.disabled||context.value!==v.context)return;const y=window.scrollY,scroll=source.value?.scrollTop||0;if(mode.value==='visual'&&editor.value){const at=editor.value.state.selection.from;editor.value.chain().focus(undefined,{scrollIntoView:false}).insertContentAt({from:at-v.length,to:at},v.text).run()}else{const el=source.value;if(!el)return;const at=el.selectionStart;publish(sourceBuffer.value.slice(0,at-v.length)+v.text+sourceBuffer.value.slice(at));queueMicrotask(()=>{el.focus({preventScroll:true});el.setSelectionRange(at-v.length+v.text.length,at-v.length+v.text.length);el.scrollTop=scroll;window.scrollTo({top:y})})}context.value=''}
function sourcePaste(e:ClipboardEvent){const files=Array.from(e.clipboardData?.files||[]);if(files.length){e.preventDefault();void upload(files)}}
function sourceDrop(e:DragEvent){void upload(Array.from(e.dataTransfer?.files||[]))}
function chooseFiles(e:Event){void upload(Array.from((e.target as HTMLInputElement).files||[]));(e.target as HTMLInputElement).value=''}
function cancel(job:Job){if(job.status==='uploading')return;jobs.value=jobs.value.filter(j=>j.key!==job.key);pending()}
async function load(){if(searching.value)return;searching.value=true;message.value='';try{const result=await request('/admin/archive/media?'+new URLSearchParams({q:q.value,page:String(page.value),page_size:'12',...(folder.value==='*'?{}:folder.value?{folder_id:folder.value}:{unfiled:'true'})}));if(alive){assets.value=result.items;total.value=result.total}}catch(e){message.value=String(e)}finally{searching.value=false}}
function openAI(){stickyOffset();if(composing.value){message.value='请先确认正在输入的文字';return}toolsTab.value='ai';aiMounted.value=true;picker.value=true}
function chooseMedia(){stickyOffset();if(composing.value){message.value='请先确认正在输入的文字';return}toolsTab.value='media';picker.value=true;if(picker.value){pickerBookmark=editor.value?markRaw(editor.value.state.selection.getBookmark()):undefined;pickerAt=mode.value==='source'?source.value?.selectionStart:undefined;void load()}}
function togglePicked(asset:Asset){chosen.value=chosen.value.some(a=>a.id===asset.id)?chosen.value.filter(a=>a.id!==asset.id):[...chosen.value,asset]}
function confirmPicked(){if(!chosen.value.length||composing.value||props.disabled)return;if(mode.value==='visual'&&!pickerBookmark||mode.value==='source'&&pickerAt===undefined){message.value='请先在正文指定图片插入位置';return;}if(!insertAssets(chosen.value,pickerBookmark,pickerAt))return;chosen.value=[];pickerBookmark=editor.value?markRaw(editor.value.state.selection.getBookmark()):undefined;if(mode.value!=='source')pickerAt=undefined}
async function link(){const url=await promptAction('链接地址（https://、http:// 或 mailto:）');if(url===null)return;if(!/^(https?:\/\/|mailto:)/i.test(url)){message.value='链接必须使用http、https或mailto协议';return}editor.value?.chain().focus(undefined,{scrollIntoView:false}).setLink({href:url}).run()}
onBeforeUnmount(()=>{stickyObserver?.disconnect();window.removeEventListener('scroll',stickyOffset,true);window.removeEventListener('resize',stickyOffset);alive=false;if(compositionFrame)cancelAnimationFrame(compositionFrame);window.removeEventListener('scroll',updateCaret,true);window.removeEventListener('resize',updateCaret);window.visualViewport?.removeEventListener('resize',updateCaret);window.visualViewport?.removeEventListener('scroll',updateCaret);for(const c of controllers)c.abort()})
type AIAnchor=AICapture&{revision:number;from:number;to:number;bookmark?:SelectionBookmark}
let aiAnchor:AIAnchor|undefined
const aiUndo=ref<{before:string;after:string;mode:'source'|'visual';format:number;revision:number}|null>(null)
const canUndoAI=computed(()=>!!aiUndo.value&&aiUndo.value.revision===documentRevision.value&&aiUndo.value.after===sourceBuffer.value&&aiUndo.value.mode===mode.value&&aiUndo.value.format===props.format&&!composing.value&&!props.disabled&&!jobs.value.some(j=>j.status!=='done'))
function captureAI():AICapture|null{
 if(composing.value||props.disabled||jobs.value.some(j=>j.status!=='done')){message.value='请先完成输入或图片上传，再选择发送范围';return null}
 const base={id:newId(),body:sourceBuffer.value,mode:mode.value,format:props.format,revision:documentRevision.value}
 if(mode.value==='source'){
  const el=source.value;if(!el)return null
  aiAnchor={...base,from:el.selectionStart,to:el.selectionEnd,selection:el.value.slice(el.selectionStart,el.selectionEnd)}
 }else{
  const e=editor.value;if(!e||e.isDestroyed)return null
  const {from,to}=e.state.selection
  const content=e.state.doc.slice(from,to).content.toJSON()||[]
  aiAnchor={...base,from,to,bookmark:markRaw(e.state.selection.getBookmark()),selection:from===to?'':e.storage.markdown.manager.serialize({type:'doc',content})}
 }
 return {...base,selection:aiAnchor.selection}
}
function applyAI(id:string,text:string,action:AIApply):boolean{
 const a=aiAnchor
 if(!a||a.id!==id||a.revision!==documentRevision.value||a.body!==sourceBuffer.value||a.mode!==mode.value||a.format!==props.format||composing.value||props.disabled||jobs.value.some(j=>j.status!=='done')){message.value='正文、模式或输入状态已变化，未应用旧AI结果，请重新选择范围';return false}
 if(action==='selection'&&a.from===a.to){message.value='原先没有选择文字，不能替换选区';return false}
 const before=sourceBuffer.value,scroll=window.scrollY
 try{
  if(mode.value==='source'){
   const patch=sourcePatch(before,a.from,a.to,text,action),el=source.value
   if(!el||el.value!==before)throw Error('当前编辑内容与生成时不同')
   // Native insertion keeps the browser's source undo where supported. The
   // explicit guarded AI undo remains available in other browsers as well.
   el.focus({preventScroll:true});el.setSelectionRange(action==='replace'?0:action==='insert'?a.to:a.from,action==='replace'?before.length:a.to)
   const native=typeof document.execCommand==='function'&&document.execCommand('insertText',false,text)
   if(!native)publish(patch.value)
   else if(el.value!==patch.value)throw Error('浏览器未按原选区插入，保留当前内容并请人工核对')
   else if(sourceBuffer.value!==patch.value)publish(patch.value)
   queueMicrotask(()=>{el.setSelectionRange(patch.caret,patch.caret);window.scrollTo({top:scroll})})
  }else{
   const e=editor.value;if(!e||e.isDestroyed||!visualCompatible(text))throw Error('结果包含当前可视化模式不支持的语法，请使用源码预览')
   const resolved=a.bookmark?.resolve(e.state.doc),from=action==='replace'?0:action==='insert'?(resolved?.to??a.to):(resolved?.from??a.from),to=action==='replace'?e.state.doc.content.size:(resolved?.to??a.to)
   e.view.dispatch(closeHistory(e.state.tr))
   if(!e.chain().insertContentAt({from,to},text,{contentType:'markdown'}).run())throw Error('选区插入失败')
   e.view.dispatch(closeHistory(e.state.tr))
  }
  aiUndo.value={before,after:sourceBuffer.value,mode:mode.value,format:props.format,revision:documentRevision.value};aiAnchor=undefined;message.value='已应用AI候选，尚未因此发布文章；可撤销本次应用';return true
 }catch(error){message.value=error instanceof Error?error.message:String(error);return false}
}
function undoAI():boolean{
 if(!canUndoAI.value||!aiUndo.value){message.value='应用后内容已有变化，不能用旧快照覆盖新输入';return false}
 const old=aiUndo.value;aiUndo.value=null
 if(mode.value==='visual'&&editor.value)editor.value.commands.undo()
 else publish(old.before)
 message.value='已撤销AI应用，原正文保留';return true
}
defineExpose({hasPending:()=>composing.value||jobs.value.some(j=>j.status!=='done'),captureAI,applyAI,undoAI})
</script>
<template><section class="body-editor" :class="{'tools-open':picker}" @compositionstart.capture="!($event.target as HTMLElement).closest('.editor-tools')&&composition(true)" @compositionend.capture="!($event.target as HTMLElement).closest('.editor-tools')&&composition(false)" @compositionupdate.capture="!($event.target as HTMLElement).closest('.editor-tools')&&composing&&pending()" :aria-busy="jobs.some(j=>j.status==='uploading')"><div ref="toolbar" class="writing-toolbar" :style="{top:toolbarTop+'px'}" role="toolbar" aria-label="正文格式"><span class="toolbar-group" role="group" aria-label="编辑模式"><button type="button" class="quiet" :disabled="disabled" @click="switchMode">{{mode==='visual'?'Markdown 源码':'可视化编辑'}}</button></span><span class="toolbar-group" role="group" aria-label="文本格式" v-if="mode==='visual'"><button type="button" class="quiet" :disabled="disabled" @click="editor?.chain().focus(undefined,{scrollIntoView:false}).setParagraph().run()">段落</button><button type="button" class="quiet" :disabled="disabled" @click="editor?.chain().focus(undefined,{scrollIntoView:false}).toggleHeading({level:2}).run()">标题</button><button type="button" class="quiet" :aria-pressed="editor?.isActive('bold')" :disabled="disabled" @click="editor?.chain().focus(undefined,{scrollIntoView:false}).toggleBold().run()">粗体</button><button type="button" class="quiet" :disabled="disabled" @click="editor?.chain().focus(undefined,{scrollIntoView:false}).toggleItalic().run()">斜体</button><button type="button" class="quiet" :disabled="disabled" @click="editor?.chain().focus(undefined,{scrollIntoView:false}).toggleBulletList().run()">列表</button><button type="button" class="quiet" :disabled="disabled" @click="editor?.chain().focus(undefined,{scrollIntoView:false}).toggleOrderedList().run()">有序列表</button><button type="button" class="quiet" :disabled="disabled" @click="editor?.chain().focus(undefined,{scrollIntoView:false}).toggleBlockquote().run()">引用</button><button type="button" class="quiet" :disabled="disabled" @click="link">链接</button><button type="button" class="quiet" :disabled="disabled" @click="editor?.chain().focus(undefined,{scrollIntoView:false}).toggleCodeBlock().run()">代码块</button><button type="button" class="quiet" :disabled="disabled" @click="editor?.chain().focus(undefined,{scrollIntoView:false}).undo().run()">撤销</button><button type="button" class="quiet" :disabled="disabled" @click="editor?.chain().focus(undefined,{scrollIntoView:false}).redo().run()">重做</button></span><span class="toolbar-group" role="group" aria-label="结构化记录"><button type="button" class="quiet" :disabled="disabled" @click="openEntry">@ 结构化记录</button></span><span class="toolbar-group" role="group" aria-label="媒体操作"><button type="button" class="quiet" :disabled="disabled" @click="fileInput?.click()">上传图片</button><button type="button" class="quiet" :disabled="disabled" @click="chooseMedia">从媒体库插图</button><button v-if="$slots.assistant" type="button" class="quiet" :disabled="disabled" @click="openAI">AI 写作助手</button></span></div>
<details class="markdown-help"><summary>Markdown 与地点标记帮助</summary><p>Tab / Shift+Tab 调整缩进（私有图片元数据块保持原样）；Esc 后按 Tab 离开编辑器，Enter 延续列表；Ctrl/Cmd+B 加粗、Ctrl/Cmd+I 斜体。输入 @ 搜索地点。使用 @f 餐厅后，缩进子列表记录就餐感受；子列表归属该次美食，不会拆成多个活动。代码块、表格和扩展语法始终保留原文。</p></details><details class="upload-folder"><summary>上传分类与文章文件夹</summary><label>上传到文件夹<FolderSelect aria-label="上传到文件夹" :key="folderGeneration" :model-value="uploadFolder" @update:model-value="uploadFolder=$event;folderExplicit=true" :disabled="disabled"/></label><button type="button" class="quiet" :disabled="disabled||!recordId||!title" @click="articleFolder">使用文章专属文件夹</button><p v-if="!recordId">首次成功保存草稿会自动创建专属文件夹；明确选择其他目录或未分类时优先保留你的选择。</p></details><input ref="fileInput" type="file" accept="image/jpeg,image/png,image/webp" multiple hidden @change="chooseFiles"/>
<button v-if="aiUndo" type="button" class="quiet" :disabled="!canUndoAI" @click="undoAI">撤销 AI 应用</button><p v-if="message" role="status" class="muted">{{message}}</p><p v-if="mode==='source'" class="muted">源码保持原文；不支持的语法不会被自动转换。可直接上传、粘贴或拖入图片；私有图片块可保存百分比宽度与对齐。</p>
<EditorContent v-if="mode==='visual'" :editor="editor"/><label v-else>记录正文（Markdown）<textarea ref="source" :disabled="disabled" maxlength="300000" rows="18" @paste="sourcePaste" @dragover.prevent @drop.prevent="sourceDrop" @compositionstart="composition(true)" @compositionend="composition(false)" @keydown="sourceKey" @blur="context=''" @click="updateCaret" @select="updateCaret" @keyup="updateCaret" @input="sourceInput"/></label>
<details v-if="mode==='source'&&sourceImages.length" class="source-image-controls"><summary>正文图片尺寸、说明与对齐（源码不转换）</summary><fieldset :disabled="disabled" v-for="(p,i) in sourceImages" :key="p.index"><legend>正文图片 {{i+1}} · {{p.media!.alt}}</legend><label>显示比例<select :aria-label="'正文图片'+(i+1)+'显示比例'" :value="p.media!.widthPercent||0" @change="changeSourceImage(p.index,{widthPercent:Number(($event.target as HTMLSelectElement).value)||undefined})"><option :value="0">保留像素宽度</option><option v-for="n in [30,60,100]" :value="n">{{n}}%</option></select></label><label>连续图片排列<select :value="p.media!.layout||'auto'" @change="changeSourceImage(p.index,{layout:($event.target as HTMLSelectElement).value as 'auto'|'single'|'grid'})"><option value="auto">自动紧凑（保留手动尺寸）</option><option value="single">保持单图</option><option value="grid">参与多图网格</option></select></label><label>对齐<select :aria-label="'正文图片'+(i+1)+'对齐'" :value="p.media!.align" @change="changeSourceImage(p.index,{align:($event.target as HTMLSelectElement).value as 'left'|'center'|'right'})"><option value="left">靠左</option><option value="center">居中</option><option value="right">靠右</option></select></label><label>图片说明<input :value="p.media!.caption" maxlength="2000" @input="changeSourceImage(p.index,{caption:($event.target as HTMLInputElement).value})"/></label></fieldset></details><PlaceSuggest ref="suggest" :context="context" :composing="composing" :anchor="anchor" @choose="choosePlace" @entry="chooseEntry"/><ul v-if="jobs.length" class="upload-results" aria-label="图片上传状态"><li v-for="job in jobs" :key="job.key">{{job.file?.name||job.asset?.filename}} · {{job.status==='done'?'已上传，随文章保存':job.status==='uploading'?'正在上传 '+(job.progress||0)+'%':job.message}}<template v-if="job.status==='error'"><button type="button" class="quiet" :disabled="disabled" @click="send(job)">重试上传</button><button type="button" class="quiet" @click="cancel(job)">取消此项</button></template></li></ul>
<details v-if="mode==='source'&&sourceCards.length"><summary>编辑正文结构化卡片（无需修改源码）</summary><EntryCard v-for="(c,index) in sourceCards" :key="c.entry.id" :entry="c.entry"><template #actions><EntryCardActions :disabled="disabled" :transfer="!!transfer" :can-up="c.at>0" :can-down="c.at+c.raw.length<sourceBuffer.length" @action="sourceAction(c,$event)"/></template></EntryCard></details><dialog ref="entryDialog" class="entry-dialog"><form v-if="entryDraft" @submit.stop.prevent="addEntry"><h2>插入结构化记录</h2><EntryForm :value="entryDraft" :disabled="disabled" @validity="entryTimeValid=$event"/><p role="status">{{entryError}}</p><footer><button type="submit">插入卡片</button><button type="button" class="quiet" @click="entryDialog?.close()">取消</button></footer></form></dialog><EditorTools :open="picker" :active="toolsTab" :has-a-i="!!$slots.assistant" :top="toolsTop" @close="picker=false" @tab="$event==='ai'?openAI():chooseMedia()"><template #media><section v-if="picker" class="inline-media-picker"><h3>选择私有媒体</h3><label>图片文件夹<FolderSelect aria-label="图片文件夹" v-model="folder" all/></label><label>搜索图片<input v-model="q" type="search" @keydown.enter.prevent="page=1;load()"/></label><button type="button" :disabled="searching" @click="page=1;load()">搜索图片</button><div v-if="largePreview" class="picker-large"><button type="button" class="quiet" @click="largePreview=null">返回缩略图</button><PrivatePreview :id="largePreview.id" :alt="largePreview.alt" variant="preview"/><p>{{largePreview.filename}}</p></div><div class="picker-grid"><article v-for="asset in assets" :key="asset.id" class="picker-photo"><button type="button" class="quiet" :aria-pressed="chosen.some(a=>a.id===asset.id)" :disabled="disabled" @click="togglePicked(asset)"><PrivatePreview :id="asset.id" :alt="asset.alt"/><span :title="asset.filename">{{asset.title||asset.filename}}</span><span>{{chosen.some(a=>a.id===asset.id)?'已选择':'选择'}}</span></button><button type="button" class="quiet" :aria-label="'放大预览 '+asset.filename" @click="largePreview=asset">放大预览</button></article></div><div class="actions"><button type="button" :disabled="searching||page<=1" @click="page--;load()">上一页</button><span>{{page}}</span><button type="button" :disabled="searching||page*12>=total" @click="page++;load()">下一页</button><button type="button" class="quiet" @click="picker=false">关闭选择器</button></div></section></template><template #footer><div v-if="toolsTab==='media'" class="actions" aria-label="媒体插入操作"><span role="status">已选择 {{chosen.length}} 张</span><button type="button" :disabled="disabled||!chosen.length||composing" @click="confirmPicked">确认插入 {{chosen.length}} 张</button><button type="button" class="quiet" :disabled="!chosen.length" @click="chosen=[]">取消选择</button></div></template><template #ai><slot v-if="aiMounted" name="assistant"/></template></EditorTools>
</section></template>
<style>
.body-editor{min-width:0;overflow:visible}.writing-toolbar{display:flex;flex-wrap:wrap;gap:4px;position:sticky;top:0;z-index:20;padding:8px 0;background:var(--paper,var(--ui-card));border-bottom:1px solid var(--line,var(--ui-line))}.writing-toolbar button{font-size:13px;min-height:40px;padding:6px 10px}.immersive-prose{min-height:45vh;outline:none;font-size:18px;line-height:1.95;padding:22px 0;overflow-wrap:anywhere}.immersive-prose:focus-visible{outline:2px solid var(--accent,var(--ui-line));outline-offset:4px}.body-editor textarea,.immersive-prose{overflow-anchor:none}.body-editor>p[role=status]{min-height:1.5em}.immersive-prose h2{font-size:1.65em}.immersive-prose p{margin:1em 0}.immersive-prose pre{white-space:pre-wrap}.writing-image img{width:100%;height:auto}.writing-image p{text-align:center;font-size:14px}.image-options{font-size:14px;border:1px solid var(--line,var(--ui-line));padding:8px}.image-options summary{cursor:pointer;min-height:40px}.picker-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.picker-grid img{width:100%;aspect-ratio:1.5;object-fit:cover}.picker-grid button{overflow-wrap:anywhere;min-width:0}.upload-results{font-size:14px;padding-left:20px}@media(max-width:600px){.immersive-prose{font-size:17px}.picker-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.writing-toolbar{position:sticky;flex-wrap:nowrap;overflow-x:auto;overscroll-behavior-inline:contain;max-width:100%;scrollbar-width:thin}.writing-toolbar .toolbar-group{flex:0 0 auto;flex-wrap:nowrap}}
</style>

<style>.body-editor details[open]>summary{font-weight:700}.body-editor summary{cursor:pointer;padding:8px 0}.body-editor summary::marker{color:var(--accent)}.writing-toolbar button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}.body-editor textarea{max-width:100%;box-sizing:border-box;font-family:ui-monospace,monospace;line-height:1.65;tab-size:2}.body-editor fieldset{min-width:0}.body-editor pre{max-width:100%;overflow:auto}</style>

<style>.toolbar-group{display:flex;flex-wrap:wrap;gap:4px;padding-right:8px;margin-right:4px;border-right:1px solid var(--line,var(--ui-line))}.toolbar-group:last-child{border-right:0}.writing-toolbar button[aria-pressed=true]{outline:2px solid var(--accent);background:var(--paper)}.writing-toolbar button:disabled{opacity:.5;cursor:not-allowed}</style>

<style>
.picker-photo{min-width:0;display:flex;flex-direction:column;gap:4px}.picker-photo>button{width:100%;min-width:0;display:flex;flex-direction:column;gap:6px}.picker-photo span{display:block;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.picker-photo button[aria-pressed=true]{outline:2px solid var(--accent);outline-offset:1px}.picker-large{min-width:0}.picker-large img{max-width:100%;height:auto}.picker-large p{overflow-wrap:anywhere}.inline-media-picker .picker-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.upload-results li{overflow-wrap:anywhere}
@media(min-width:1180px){.body-editor.tools-open{padding-inline-end:380px}}
</style>

<style>.entry-dialog{width:min(640px,calc(100vw - 32px));max-height:85dvh;overflow:auto;background:var(--paper);color:var(--ink);border:1px solid var(--line);box-sizing:border-box}.entry-dialog footer{position:sticky;bottom:0;padding:12px 0 max(12px,env(safe-area-inset-bottom));background:var(--paper);display:flex;gap:8px;flex-wrap:wrap}</style>
