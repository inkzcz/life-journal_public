<script setup lang="ts">
import { ref,onMounted,onBeforeUnmount,watch,nextTick } from 'vue'
import type { Heading } from './markdown'
import { readingProgress,currentHeading,visibleReadingTarget } from './tracking'
const props=defineProps<{hash?:string;embedded?:boolean;context?:{title:string;type:string;date:string}}>()
const emit=defineEmits<{(e:'anchor',id:string):void}>()
const frame=ref<HTMLElement|null>(null),content=ref<HTMLElement|null>(null),toc=ref<HTMLDetailsElement|null>(null)
const focused=ref(false),contextOpen=ref(true)
const headings=ref<Heading[]>([]),active=ref(''),progress=ref(0)
let root:HTMLElement|null=null,observer:ResizeObserver|undefined,mutations:MutationObserver|undefined,raf=0,dead=false
let wide:boolean|undefined
let start=0,height=0,viewport=1,offsets:number[]=[],nodes:HTMLElement[]=[]
const scroll=()=>root?root.scrollTop:window.scrollY
function update(){raf=0;if(dead)return;const position=scroll();progress.value=readingProgress(position,start,height,viewport);active.value=headings.value[currentHeading(offsets,position,viewport)]?.id||''}
function schedule(){if(!raf)raf=requestAnimationFrame(update)}
function measure(){
 if(!content.value||dead)return
 const nextWide=(frame.value?.getBoundingClientRect().width||0)>=1050
 if(toc.value&&nextWide!==wide){wide=nextWide;toc.value.open=nextWide}
 const origin=root?root.getBoundingClientRect().top+root.clientTop:0,position=scroll()
 viewport=root?root.clientHeight:window.innerHeight
 const rect=content.value.getBoundingClientRect();start=rect.top-origin+position;height=rect.height
 offsets=nodes.map(node=>visibleReadingTarget(node,content.value!).getBoundingClientRect().top-origin+position);schedule()
}
function jump(id:string){
 const node=nodes.find(node=>node.id===id);if(!node)return
 let parent=node.parentElement;while(parent&&parent!==content.value){if(parent instanceof HTMLDetailsElement)parent.open=true;parent=parent.parentElement}
 // Collapse before measuring: a mobile TOC changes the article's top offset.
 if(toc.value&&(frame.value?.getBoundingClientRect().width||0)<1050)toc.value.open=false
 measure();const top=offsets[nodes.indexOf(node)]!-80
 if(root)root.scrollTo({top,behavior:'auto'});else window.scrollTo({top,behavior:'auto'})
 node.focus({preventScroll:true});schedule()
}
function fromHash(){if(!props.hash)return;try{jump(decodeURIComponent(props.hash.slice(1)))}catch{/* Invalid fragments are inert. */}}
function choose(id:string){if(props.embedded||props.hash==='#'+id)jump(id);else emit('anchor',id)}
watch(()=>props.hash,()=>void nextTick(fromHash))
function refreshHeadings(){
 if(!content.value||dead)return
 nodes=Array.from(content.value.querySelectorAll<HTMLElement>('.article-body [data-reading-heading],.template-module>h2,.article-gallery>h2,.reading-places>h2,.related-stories>h2,.article-heading h1,.trip-view,.place-map'))
 nodes=nodes.filter(node=>!node.classList.contains('place-map')||!node.closest('.template-module')&&!!node.querySelector('.map-place-list button'))
 nodes.forEach((node,index)=>{if(!node.id){node.id='lj-reader-section-'+index;node.tabIndex=-1}})
 headings.value=nodes.map(node=>({id:node.id,text:node.classList.contains('trip-view')?'旅行行程':node.classList.contains('place-map')?'路线与地点':node.textContent?.trim()||'未命名章节',level:/^H[1-6]$/.test(node.tagName)?Number(node.tagName[1]):2}))
}
onMounted(async()=>{
 await nextTick();if(dead||!content.value)return
 root=frame.value?.closest<HTMLElement>('.editor-preview-scroll')||null
 refreshHeadings()
 mutations=new MutationObserver(()=>{refreshHeadings();measure()});mutations.observe(content.value,{childList:true,subtree:true})
 ;(root||window).addEventListener('scroll',schedule,{passive:true});window.addEventListener('resize',measure)
 content.value.addEventListener('load',measure,true);content.value.addEventListener('toggle',measure,true)
 if(typeof ResizeObserver!=='undefined'){observer=new ResizeObserver(measure);observer.observe(content.value);if(root)observer.observe(root)}
 measure();await nextTick();if(toc.value)toc.value.open=(frame.value?.getBoundingClientRect().width||0)>=1050;fromHash()
})
onBeforeUnmount(()=>{dead=true;cancelAnimationFrame(raf);observer?.disconnect();mutations?.disconnect();(root||window).removeEventListener('scroll',schedule);window.removeEventListener('resize',measure);content.value?.removeEventListener('load',measure,true);content.value?.removeEventListener('toggle',measure,true)})
</script>
<template><div ref="frame" class="reading-frame" :class="{'is-focused':focused}"><div class="reading-tools"><button type="button" :aria-pressed="focused" @click="focused=!focused;nextTick(measure)">{{focused?'退出专注阅读':'专注阅读'}}</button><button v-if="context&&!focused" type="button" :aria-expanded="contextOpen" @click="contextOpen=!contextOpen;nextTick(measure)">{{contextOpen?'收起文章信息':'显示文章信息'}}</button></div>
<div class="reading-progress" role="progressbar" aria-label="文章阅读进度" :aria-valuenow="progress" aria-valuemin="0" aria-valuemax="100" :class="{'progress-embedded':embedded}"><span :style="{transform:'scaleX('+progress/100+')'}"></span></div>
<div class="reading-layout" :class="{'has-toc':headings.length>=1,'has-context':context&&contextOpen&&!focused}">
<details v-if="headings.length>=1" ref="toc" class="reading-toc" @toggle="measure"><summary>本文目录 <span aria-hidden="true">⌄</span></summary><nav aria-label="本文目录"><a v-for="h in headings" :key="h.id" :href="'#'+h.id" :data-level="h.level" :aria-current="active===h.id?'location':undefined" @click.prevent="choose(h.id)">{{h.text}}</a></nav></details>
<article ref="content" class="reading-article"><slot /></article><aside v-if="context&&contextOpen&&!focused" class="reading-context" aria-label="文章信息"><h2>{{context.title}}</h2><p>{{context.type}} · {{context.date}}</p><p>私人生活档案 · 图片与地点仅向登录用户展示</p></aside>
</div></div></template>
