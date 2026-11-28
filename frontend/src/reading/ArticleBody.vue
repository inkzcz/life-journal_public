<script setup lang="ts">
import {loadTypography,saved,type ReaderMode} from '../presentation/typography'
import {computed,onMounted,provide,ref,watch,nextTick,useId} from 'vue'
import {bodyTree,compactBody,type MediaBlock,type BodyNode} from '../writing/body'
import {entryNames,type Entry,type EntryKind} from '../writing/entries'
import BodyNodes,{type RenderedBodyNode} from './BodyNodes.vue'
import {articleMarkdown} from './markdown'
import {readingPreview,type PreviewImage} from './mediaPreview'
const props=defineProps<{source:string;namespace:string;format?:number;previewMedia?:PreviewImage[]}>()
provide(readingPreview,computed(()=>props.previewMedia))
const localMode=ref<ReaderMode|null>(null),filter=ref<EntryKind|'all'>('all'),container=ref<HTMLElement|null>(null)
const dialog=ref<HTMLDialogElement|null>(null),selected=ref<Entry|null>(null),closeButton=ref<HTMLButtonElement|null>(null),dialogTitle=useId()
let opener:HTMLElement|null=null
const mode=computed(()=>localMode.value||saved.value.reader_mode||'full')
onMounted(()=>void loadTypography())
watch(()=>[props.source,props.namespace,props.format],()=>{localMode.value=null;filter.value='all';close()})
const rendered=computed(()=>{
 const tree=bodyTree(props.source,props.format||1)
 let offset=0
 function render(nodes:BodyNode[]):RenderedBodyNode[]{return nodes.map(node=>{
  if(node.children)return {...node,children:render(node.children)}
  if(node.entry||node.media||node.gallery)return node
  const result=articleMarkdown(node.source||'',props.namespace,offset,tree.links);offset+=result.headings.length
  return {...node,html:result.html}
 })}
 return render(compactBody(tree))
})
const entries=computed(()=>{const collect=(nodes:BodyNode[]):Entry[]=>nodes.flatMap(n=>n.entry?[n.entry]:n.children?collect(n.children):[]);return collect(rendered.value)})
const counts=computed(()=>Object.fromEntries(Object.keys(entryNames).map(kind=>[kind,entries.value.filter(e=>e.kind===kind).length])))
const filtered=computed(()=>entries.value.filter(e=>filter.value==='all'||e.kind===filter.value))
const photos=computed(()=>{const collect=(nodes:BodyNode[]):MediaBlock[]=>nodes.flatMap(n=>n.entry?mode.value==='plain'?[]:entryMedia(n.entry):n.gallery||(n.media?[n.media]:n.children?collect(n.children):[]));return collect(rendered.value)})
function entryMedia(entry:Entry):MediaBlock[]{return entry.media_ids.map(id=>({id,alt:entry.name,caption:'',width:960,align:'center'}))}
async function open(entry:Entry,event:MouseEvent){opener=event.currentTarget as HTMLElement;selected.value=entry;await nextTick();dialog.value?.showModal();closeButton.value?.focus()}
function close(){if(dialog.value?.open)dialog.value.close();selected.value=null;opener?.focus({preventScroll:true});opener=null}
async function jump(id:string){localMode.value='full';await nextTick();const node=Array.from(container.value?.querySelectorAll<HTMLElement>('[id]')||[]).find(el=>el.id==='entry-'+id);node?.scrollIntoView({block:'center',behavior:'auto'});node?.focus({preventScroll:true})}
</script>
<template><div ref="container" class="blog-prose article-body"><nav v-if="entries.length" class="article-modes" aria-label="文章阅读模式"><button v-for="(label,key) in {full:'完整阅读',plain:'纯正文',cards:'卡片汇总'}" :key="key" type="button" :aria-pressed="mode===key" @click="localMode=key">{{label}}</button></nav><template v-if="mode==='cards'&&entries.length"><nav class="article-modes" aria-label="卡片分类"><button type="button" :aria-pressed="filter==='all'" @click="filter='all'">全部 ({{entries.length}})</button><template v-for="(label,kind) in entryNames" :key="kind"><button v-if="counts[kind]" type="button" :aria-pressed="filter===kind" @click="filter=kind">{{label}} ({{counts[kind]}})</button></template></nav><section aria-label="本文卡片汇总"><div v-for="entry in filtered" :key="entry.id" class="summary-entry"><BodyNodes :nodes="[{entry}]" :photos="photos"/><button type="button" @click="jump(entry.id)">定位至正文 · {{entry.name}}</button></div></section></template><BodyNodes v-else :nodes="rendered" :photos="photos" :plain="mode==='plain'" @open="open"/><dialog ref="dialog" class="entry-reader-dialog" :aria-labelledby="dialogTitle" @cancel.prevent="close" @close="close"><template v-if="selected"><h2 :id="dialogTitle">{{selected.name}}</h2><button ref="closeButton" type="button" @click="close">关闭卡片</button><BodyNodes :nodes="[{entry:selected}]" :photos="entryMedia(selected)"/></template></dialog></div></template>
<style scoped>.article-modes{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}.article-modes button{font:inherit}.article-modes [aria-pressed=true]{outline:2px solid currentColor;outline-offset:1px}.summary-entry{margin:16px 0;min-width:0}.entry-reader-dialog{width:min(820px,calc(100vw - 32px));max-height:85dvh;overflow:auto;color:inherit;background:var(--surface,var(--ui-modal));border:1px solid var(--line,var(--ui-line));padding:16px;box-sizing:border-box}.entry-reader-dialog::backdrop{background:rgb(0 0 0 / .4)}</style>
