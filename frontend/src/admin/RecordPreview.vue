<script setup lang="ts">
import { ref,onMounted } from 'vue'
import BlogView from '../blog/BlogView.vue'
defineProps<{record:{id:string;revision:number;status:string}}>()
const emit=defineEmits<{(e:'close'):void}>()
const dialog=ref<HTMLDialogElement|null>(null),size=ref<'desktop'|'mobile'>('desktop')
onMounted(()=>dialog.value?.showModal())
function navigate(path:string){window.open(path,'_blank','noopener')}
</script>
<template><dialog ref="dialog" class="editor-preview" aria-label="真实文章预览" @close="emit('close')">
<header class="editor-preview-controls"><div><h2>{{record.status==='draft'?'未发布预览':'已发布记录的管理预览'}}</h2><p>只读 · 已保存修订 {{record.revision}} · 预览不会发布或创建修订</p></div><div class="actions"><label>预览布局<select v-model="size" aria-label="预览布局"><option value="desktop">电脑画布（1280px）</option><option value="mobile">手机画布（390px）</option></select></label><button autofocus type="button" @click="dialog?.close()">返回编辑</button></div></header>
<p class="muted">画布可横向滚动，主题与配色取自实际站点；关联链接在新标签页打开。</p>
<div class="editor-preview-scroll"><div class="editor-preview-canvas" :style="{width:(size==='mobile'?390:1280)+'px'}"><BlogView embedded :target="'/preview/posts/'+record.id+'?revision='+record.revision" @navigate="navigate" /></div></div>
</dialog></template>
<style scoped>
.editor-preview{width:min(1500px,96vw);max-width:96vw;height:94dvh;max-height:94dvh;padding:20px;background:var(--studio-paper,var(--ui-card));color:var(--studio-ink,var(--ui-ink));border:1px solid var(--studio-line,var(--ui-line));border-radius:var(--ui-radius);overflow:auto}
.editor-preview::backdrop{background:var(--ui-primary)}.editor-preview-controls{position:sticky;top:-20px;z-index:2;background:var(--studio-paper,var(--ui-card));display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap;padding:12px 0}.editor-preview-controls h2{margin:0}.editor-preview-controls p{margin:8px 0;font-size:13px}.editor-preview-controls label{margin:0;font-weight:400}.editor-preview-scroll{overflow:auto;max-width:100%;max-height:68dvh;overscroll-behavior:contain;border:1px solid var(--studio-line,var(--ui-line))}.editor-preview-canvas{container-type:inline-size;max-width:none}.editor-preview-canvas :deep(.blog){min-height:60vh}
@media(max-width:600px){.editor-preview{padding:12px}.editor-preview-controls{top:-12px;gap:8px}.editor-preview-controls h2{font-size:20px}.editor-preview-controls .actions{width:100%;justify-content:space-between}.editor-preview-controls label{flex:1;min-width:0}}
</style>
