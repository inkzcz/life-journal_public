<script setup lang="ts">
import {computed,ref,nextTick,watch,inject} from 'vue'
import PrivatePreview from '../admin/PrivatePreview.vue'
import {mediaStyle,type MediaBlock} from '../writing/body'
import {request} from '../api'
import {mediaRequest} from '../admin/mediaRequests'
import {readingPreview,previewImage} from './mediaPreview'
const props=defineProps<{images:MediaBlock[];photos:MediaBlock[]}>()
const preview=inject(readingPreview,undefined),previewFailures=ref<Record<string,boolean>>({})
const previewContext=computed(()=>preview?.value!==undefined)
const candidateImage=(id:string)=>previewImage(preview?.value,id)
const index=ref(-1),dialog=ref<HTMLDialogElement|null>(null),admin=ref(false),message=ref(''),current=computed(()=>props.photos[index.value])
let touchX=0,touchY=0
async function open(m:MediaBlock){index.value=props.photos.indexOf(m);await nextTick();dialog.value?.showModal();try{admin.value=(await request('/admin/status')).is_admin}catch{admin.value=false}}
function close(){dialog.value?.close();index.value=-1}
function next(n:number){if(props.photos.length)index.value=(index.value+n+props.photos.length)%props.photos.length}
function swipe(e:TouchEvent){const end=e.changedTouches[0];if(end&&Math.abs(end.clientX-touchX)>45&&Math.abs(end.clientX-touchX)>Math.abs(end.clientY-touchY))next(end.clientX<touchX?1:-1)}
watch(()=>props.photos,()=>{close();previewFailures.value={}})
watch(()=>preview?.value,()=>{previewFailures.value={}})
async function original(){if(!current.value)return;try{const blob=await mediaRequest('/library-media/'+current.value.id+'/original',new AbortController().signal),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=current.value.id;a.click();setTimeout(()=>URL.revokeObjectURL(url),2000)}catch(e){message.value='原图需要管理员权限，下载失败：'+String(e)}}
</script>
<template><div class="inline-media" :class="{'inline-media-grid':images.length>1}" :data-count="images.length"><figure v-for="(m,i) in images" :key="i" :style="images.length===1?mediaStyle(m):undefined"><div v-if="previewContext" class="body-photo-button body-photo-preview"><img v-if="candidateImage(m.id)&&!previewFailures[m.id]" :src="candidateImage(m.id)!.url" :alt="m.alt" :width="candidateImage(m.id)!.width" :height="candidateImage(m.id)!.height" loading="lazy" decoding="async" @error="previewFailures[m.id]=true"><span v-else class="private-image-status">此预览中的图片暂不可用，请重新校验</span></div><button v-else type="button" class="body-photo-button" :aria-label="'放大图片：'+(m.alt||'正文照片')" @click="open(m)"><PrivatePreview :id="m.id" :alt="m.alt" variant="preview"/></button><figcaption v-if="m.caption">{{m.caption}}</figcaption></figure></div><dialog ref="dialog" class="lightbox inline-lightbox" aria-label="正文图片浏览" @close="index=-1" @keydown.left.prevent="next(-1)" @keydown.right.prevent="next(1)" @click="($event.target===dialog)&&close()" @touchstart.passive="touchX=$event.touches[0]?.clientX||0;touchY=$event.touches[0]?.clientY||0" @touchend.passive="swipe"><template v-if="current"><div class="gallery-controls"><button autofocus @click="close">关闭图片</button><button :disabled="photos.length<2" @click="next(-1)">上一张</button><span>{{index+1}} / {{photos.length}}</span><button :disabled="photos.length<2" @click="next(1)">下一张</button><button v-if="admin" @click="original">下载原图（管理员）</button></div><PrivatePreview :id="current.id" :alt="current.alt" variant="preview" eager/><p>{{current.caption}}</p><p v-if="message" role="status">{{message}}</p></template></dialog></template>
<style>
.inline-media{min-width:0;margin-block:18px}.article-body .inline-media figure{min-width:0;margin:0}.body-photo-button{display:block;width:100%;padding:0!important;border:0!important;background:transparent!important;cursor:zoom-in}.body-photo-preview{cursor:default}.body-photo-button img{display:block;width:100%;height:auto;max-height:75vh;object-fit:contain}.inline-media-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;align-items:start}.inline-media-grid[data-count="3"]{grid-template-columns:repeat(3,minmax(0,1fr))}.inline-media-grid .body-photo-button{aspect-ratio:4/3;background:var(--surface)!important}.inline-media-grid .body-photo-button img{width:100%;height:100%!important;object-fit:contain}.inline-media figcaption{font-size:.85em;color:var(--muted);overflow-wrap:anywhere}.inline-lightbox{max-width:min(96vw,1400px);max-height:94dvh;overflow:auto}.inline-lightbox img{width:100%;height:auto;max-height:76dvh;object-fit:contain}.inline-lightbox .gallery-controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center}@media(max-width:600px){.inline-media-grid,.inline-media-grid[data-count="3"]{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.inline-lightbox{padding:12px}}
</style>
