<script setup lang="ts">
import {computed,ref,watch} from 'vue'
import PrivatePreview from '../admin/PrivatePreview.vue'
import type {Connections} from '../admin/archive'
const props=defineProps<{modelValue:string[];media:Connections['media'];disabled:boolean}>()
const emit=defineEmits<{(e:'update:modelValue',value:string[]):void}>()
const query=ref(''),preview=ref(''),dialog=ref<HTMLDialogElement|null>(null)
const filtered=computed(()=>props.media.filter(m=>[m.asset.title,m.asset.filename,m.asset.alt].join(' ').toLocaleLowerCase().includes(query.value.toLocaleLowerCase())))
function toggle(id:string){if(props.disabled)return;emit('update:modelValue',props.modelValue.includes(id)?props.modelValue.filter(value=>value!==id):[...props.modelValue,id])}
watch(preview,id=>{if(id)dialog.value?.showModal();else dialog.value?.close()})
</script>
<template><section class="activity-media-picker" aria-label="活动照片选择"><label>筛选活动照片<input v-model="query" placeholder="图片标题或文件名" :disabled="disabled"/></label><p>{{modelValue.length}} 张已选；取消关联不会删除原图。</p><div class="activity-media-grid"><div v-for="item in filtered" :key="item.id" :class="{selected:modelValue.includes(item.id)}"><label><input type="checkbox" :checked="modelValue.includes(item.id)" :disabled="disabled" @change="toggle(item.id)"/><PrivatePreview :id="item.id" :alt="item.asset.alt"/><span>{{item.asset.title||item.asset.filename}}</span></label><button type="button" class="quiet" @click="preview=item.id">预览图片</button></div></div><p v-if="!filtered.length">没有匹配照片；可先在正文上传或插入图片。</p><dialog ref="dialog" aria-label="活动照片预览" @close="preview=''" @click="($event.target===dialog)&&(preview='')"><button type="button" autofocus @click="preview=''">关闭预览</button><PrivatePreview v-if="preview" :id="preview" alt="活动照片" variant="preview"/></dialog></section></template>
<style scoped>.activity-media-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,140px),1fr));gap:12px}.activity-media-grid>div{border:1px solid var(--line);border-radius:var(--ui-radius);padding:8px;min-width:0}.activity-media-grid .selected{outline:2px solid var(--accent);outline-offset:1px}.activity-media-grid label{margin:0;overflow-wrap:anywhere}.activity-media-grid input[type=checkbox]{width:auto;margin-right:8px}.activity-media-grid img{width:100%;aspect-ratio:1.4;object-fit:cover}.activity-media-picker dialog{max-width:min(90vw,900px);background:var(--surface);color:var(--ink);border:1px solid var(--line);border-radius:var(--ui-radius)}.activity-media-picker dialog img{max-height:75dvh;width:100%;object-fit:contain}</style>
