<script setup lang="ts">
import {ref,watch,nextTick,onMounted,onBeforeUnmount} from 'vue'
import {request} from '../api'
import {popupPosition,suggestionMatch,type Caret} from './caret'
import {entryNames,type EntryKind} from './entries'
import {placeKinds} from './places'
const props=defineProps<{context:string;composing:boolean;anchor?:Caret}>()
const emit=defineEmits<{(e:'choose',value:{length:number;text:string;context:string}):void;(e:'entry',value:{length:number;context:string;kind:EntryKind}):void}>()
const options=ref<{label:string;text:string;entry?:EntryKind}[]>([]),index=ref(0),length=ref(0),message=ref('')
const panel=ref<HTMLElement|null>(null),position=ref({left:8,top:8})
function place(){if(panel.value&&props.anchor){panel.value.style.maxHeight=Math.max(0,(window.visualViewport?.height||innerHeight)-16)+'px';panel.value.style.overflowY='auto';const r=panel.value.getBoundingClientRect();position.value=popupPosition(props.anchor,r.width,r.height)}}
watch(()=>[props.anchor,options.value,message.value],()=>void nextTick(place))
onMounted(()=>{window.addEventListener('resize',place);window.visualViewport?.addEventListener('resize',place)})
let generation=0,timer:ReturnType<typeof setTimeout>|undefined
watch(()=>[props.context,props.composing],()=>{clearTimeout(timer);const seq=++generation;options.value=[];message.value='';if(props.composing)return;const match=suggestionMatch(props.context);if(!match)return;length.value=match[1]!.length;index.value=0;const kind=match[2],query=match[3]?.trim()||'';if(!kind){options.value=[...placeKinds.filter(k=>['l','f'].includes(k.kind)).map(k=>({label:'@'+k.kind+' '+k.label,text:'@'+k.kind+' '})),...Object.entries(entryNames).map(([kind,label])=>({label:'@'+kind+' '+label+'卡片',text:'@'+kind,entry:kind as EntryKind})),...placeKinds.filter(k=>!['l','f'].includes(k.kind)).map(k=>({label:'原有地点语法：@'+k.kind+' '+k.label,text:'@'+k.kind+' '}))];return}
 timer=setTimeout(async()=>{try{const result=await request('/admin/archive/places?'+new URLSearchParams({q:query,page_size:'12'}));if(seq!==generation)return;options.value=result.items.filter((p:any)=>p.active).map((p:any)=>({label:[p.name,p.region,p.city,p.category].filter(Boolean).join(' · '),text:p.name.includes(']')?`@${kind} ${p.name} {#place:${p.id}} `:`@${kind}[${p.name}] {#place:${p.id}} `}));message.value='可继续输入新名称，无需选择；同名地点请核对地区与类型。'}catch{if(seq===generation)message.value='地点搜索暂不可用，可继续输入新名称。'}},180)
},{immediate:true})
function choose(i:number){const item=options.value[i];if(item){if(item.entry)emit('entry',{length:length.value,context:props.context,kind:item.entry});else emit('choose',{length:length.value,text:item.text,context:props.context});options.value=[]}}
function key(e:KeyboardEvent){if(props.composing||e.isComposing)return false;if(e.key==='Escape'){clearTimeout(timer);generation++;options.value=[];message.value='';return false}if(!options.value.length)return false;if(e.key==='ArrowDown'||e.key==='ArrowUp'){index.value=(index.value+(e.key==='ArrowDown'?1:-1)+options.value.length)%options.value.length;e.preventDefault();return true}if(e.key==='Enter'){choose(index.value);e.preventDefault();return true}return false}
defineExpose({key})
onBeforeUnmount(()=>{generation++;clearTimeout(timer);window.removeEventListener('resize',place);window.visualViewport?.removeEventListener('resize',place)})
</script>
<template><aside ref="panel" :style="anchor?{left:position.left+'px',top:position.top+'px',bottom:'auto',right:'auto'}:{}" v-if="options.length||message" class="place-suggestions" aria-label="地点标记补全"><div role="listbox"><button v-for="(o,i) in options" :key="o.text" type="button" role="option" :aria-selected="index===i" @pointerdown.prevent @mousedown.prevent @click="choose(i)">{{o.label}}</button></div><small>{{message||'↑↓ 选择，Enter 确认，Esc 关闭'}}</small></aside></template>
<style scoped>.place-suggestions{position:fixed;bottom:18px;right:18px;z-index:30;max-width:min(380px,calc(100vw - 36px));background:var(--surface,var(--paper,var(--ui-card)));color:var(--ink);border:1px solid var(--line);padding:12px;box-shadow:var(--ui-shadow)}.place-suggestions [role=listbox]{max-height:min(240px,35dvh);overflow:auto}.place-suggestions button{display:block;width:100%;text-align:left;font-size:14px}.place-suggestions [aria-selected=true]{outline:2px solid var(--accent);outline-offset:-2px}</style>
