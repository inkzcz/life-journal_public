<script setup lang="ts">
import { ref,watch,onMounted,onUnmounted,nextTick,computed } from 'vue'
import {mediaRequest} from './mediaRequests'
const props=withDefaults(defineProps<{id:string;alt:string;width?:number|null;height?:number|null;variant?:'thumbnail'|'preview';family?:'library'|'legacy'|'trash';eager?:boolean}>(),{variant:'thumbnail',family:'library',eager:false})
const src=ref(''),error=ref(false),anchor=ref<HTMLElement|null>(null)
const dimensions=computed(()=>props.width&&props.height?{width:props.width,height:props.height}:undefined)
// Guard stale async completions and cancel both queued and active private transfers.
let generation=0,alive=true,observer:IntersectionObserver|undefined,controller:AbortController|undefined
function clear(){if(src.value)URL.revokeObjectURL(src.value);src.value=''}
async function load(current:number){
 if(current!==generation||!alive||controller)return
 observer?.disconnect();controller=new AbortController()
 const path=props.family==='legacy'?'/media/'+encodeURIComponent(props.id)+'/preview':props.family==='trash'?'/admin/archive/media-trash/'+encodeURIComponent(props.id)+'/preview':'/library-media/'+encodeURIComponent(props.id)+'/'+props.variant
 try{const blob=await mediaRequest(path,controller.signal);if(alive&&current===generation)src.value=URL.createObjectURL(blob)}catch(e){if(alive&&current===generation&&(e as Error).name!=='AbortError')error.value=true}
}
// Native img.loading cannot defer a Blob that was already fetched.
async function observe(){
 const current=++generation;observer?.disconnect();controller?.abort();controller=undefined;clear();error.value=false
 await nextTick();if(!alive||current!==generation)return
 if(props.eager||typeof IntersectionObserver==='undefined'){void load(current);return}
 observer=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting))void load(current)},{rootMargin:'400px'})
 if(anchor.value)observer.observe(anchor.value)
}
watch(()=>[props.id,props.variant,props.family,props.eager],()=>void observe())
onMounted(()=>void observe());onUnmounted(()=>{alive=false;generation++;observer?.disconnect();controller?.abort();clear()})
</script>
<!-- Explicit ratio also protects Blob decode: reader CSS overrides the native width/height hint. -->
<template><img v-if="src&&!error" :src="src" :alt="alt" :width="dimensions?.width" :height="dimensions?.height" :style="dimensions?{aspectRatio:dimensions.width+'/'+dimensions.height}:undefined" loading="lazy" decoding="async" @error="error=true;clear()" /><span v-else ref="anchor" class="private-image-status" :class="{'image-unavailable':error}" :style="{display:'block',aspectRatio:dimensions?dimensions.width+'/'+dimensions.height:'var(--ratio,1.5)'}">{{error?'图片暂不可用':'加载图片…'}}</span></template>
