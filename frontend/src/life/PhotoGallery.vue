<script setup lang="ts">
import { computed,ref,watch,nextTick,onMounted,onUnmounted } from 'vue'
import PrivatePreview from '../admin/PrivatePreview.vue'
import { photoGroups,type PhotoNote } from './types'
const props=withDefaults(defineProps<{photos:any[];notes?:PhotoNote[];places?:any[];layout?:string;groupBy?:string}>(),{notes:()=>[],places:()=>[],layout:'grid',groupBy:'none'})
const gallery=ref<HTMLElement|null>(null),masonryReady=ref(false)
let observer:ResizeObserver|undefined
function measure(){
 masonryReady.value=props.layout==='masonry'&&!!observer
 gallery.value?.querySelectorAll<HTMLElement>('.template-photos>figure').forEach(figure=>{
  if(!masonryReady.value){figure.style.gridRowEnd='';return}
  const height=Array.from(figure.children).reduce((sum,el)=>sum+el.getBoundingClientRect().height,0)
  figure.style.gridRowEnd='span '+Math.max(1,Math.ceil((height+20)/8))
 })
}
async function observe(){await nextTick();observer?.disconnect();gallery.value?.querySelectorAll('.photo-button,figcaption,.template-photos').forEach(el=>observer?.observe(el));measure()}
onMounted(()=>{if(typeof ResizeObserver!=='undefined')observer=new ResizeObserver(measure);void observe()})
onUnmounted(()=>observer?.disconnect())
watch(()=>[props.photos,props.notes,props.groupBy,props.layout],observe,{deep:true})
const groups=computed(()=>photoGroups(props.photos,props.notes,props.places,props.groupBy)),index=ref(-1),dialog=ref<HTMLDialogElement|null>(null),current=computed(()=>props.photos[index.value])
watch(index,async i=>{if(i>=0){await nextTick();if(!dialog.value?.open)dialog.value?.showModal()}else dialog.value?.close()})
function next(d:number){if(props.photos.length)index.value=(index.value+d+props.photos.length)%props.photos.length}
// A record can change while a gallery is open; never retain a stale media index.
watch(()=>props.photos,()=>{index.value=-1})
</script>
<template><div ref="gallery" class="enhanced-gallery" :class="['photo-layout-'+layout,{'masonry-ready':masonryReady}]"><section v-for="g in groups" :key="g.name" class="photo-group"><h3 v-if="g.name">{{g.name}}</h3><div class="template-photos"><figure v-for="p in g.photos" :key="p.id"><button class="photo-button" :aria-label="'放大图片：'+(p.alt||p.title||'生活影像')" @click="index=photos.findIndex(x=>x.id===p.id)"><PrivatePreview :variant="layout==='large'?'preview':'thumbnail'" :id="p.id" :alt="p.alt" :width="p.width" :height="p.height" /></button><figcaption>{{p.caption||p.title}}</figcaption></figure></div></section>
<dialog ref="dialog" class="lightbox gallery-lightbox" aria-label="相册图片浏览" @close="index=-1" @keydown.left.prevent="next(-1)" @keydown.right.prevent="next(1)" @click="($event.target===dialog)&&(index=-1)"><template v-if="current"><div class="gallery-controls"><button autofocus @click="index=-1">关闭图片</button><button :disabled="photos.length<2" @click="next(-1)">上一张</button><span>{{index+1}} / {{photos.length}}</span><button :disabled="photos.length<2" @click="next(1)">下一张</button></div><PrivatePreview :id="current.id" :alt="current.alt" variant="preview" :eager="true" :width="current.width" :height="current.height" /><p>{{current.caption||current.title}}</p></template></dialog></div></template>
<style scoped>
.enhanced-gallery{container-type:inline-size}
.template-photos{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px;align-items:start}
.template-photos figure{margin:0;min-width:0;align-self:start}
.template-photos img{width:100%;display:block;aspect-ratio:auto;height:auto;object-fit:contain;border-radius:var(--radius,6px)}
figcaption{font-size:14px;line-height:1.7;color:var(--reader-muted-text,var(--muted));padding:10px 0;overflow-wrap:anywhere}
/* Row-major placement, no dense packing and no columns: DOM and visual order agree. */
.photo-layout-masonry.masonry-ready .template-photos{grid-auto-rows:8px;row-gap:0}
.photo-layout-large .template-photos{grid-template-columns:1fr}
.photo-layout-large img{max-height:900px;object-fit:contain}
.photo-group{margin-bottom:32px}.gallery-controls{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:16px}
.gallery-lightbox img{width:100%;max-height:75vh;object-fit:contain}.gallery-controls span{color:var(--reader-body-text,var(--ink))}
@media(min-width:1000px){.photo-layout-masonry .template-photos{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:600px){.template-photos{gap:12px}.photo-layout-masonry .template-photos{row-gap:0}.gallery-controls{gap:8px}.gallery-controls button{padding:8px}}
@media(max-width:350px){.template-photos{grid-template-columns:1fr}}
@container(max-width:20rem){.template-photos{grid-template-columns:1fr}}
</style>
