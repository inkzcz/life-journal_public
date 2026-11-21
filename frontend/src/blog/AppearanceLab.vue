<script setup lang="ts">
import {computed,onMounted,provide,ref} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {request} from '../api'
import {styles,palettes,type Appearance,type Style,type PaletteName} from './types'
import WritePage from '../writing/WritePage.vue'
import BlogView from './BlogView.vue'
import './appearance-lab.css'
const route=useRoute(),router=useRouter(),candidate=ref('garden'),view=ref('writing'),records=ref<any[]>([]),error=ref('')
const style=ref<Style>('modern-soft'),palette=ref<PaletteName>('celadon'),mode=ref<'light'|'dark'|'system'>('light')
const appearance=computed<Appearance>(()=>({theme:'celadon',style:style.value,palette:palette.value,mode:mode.value}))
provide('appearanceCandidate',candidate)
onMounted(async()=>{try{records.value=(await request('/admin/content/records?page_size=100')).items}catch(e){error.value=String(e)}})
</script>
<template><main class="appearance-lab" :data-candidate="candidate"><header class="lab-controls"><RouterLink to="/admin/site">返回外观设置</RouterLink><h1>视觉实验室 · 纸笺花园已选定</h1><p>只读呈现真实页面；以下选择仅存在本页内存，不保存外观，不修改文章。正式页面采用 A「纸笺花园」；B 仅保留作历史对照，实验选项不写入站点。</p><p v-if="error" role="alert">{{error}}</p><div class="lab-choices"><label>候选方案<select v-model="candidate" aria-label="候选方案"><option value="garden">A · 纸笺花园（已选定）</option><option value="folio">B · 旅人手札（历史对照）</option></select></label><label>风格<select v-model="style" aria-label="候选风格"><option v-for="(name,key) in styles" :key="key" :value="key">{{name}}</option></select></label><label>配色<select v-model="palette" aria-label="候选配色"><option v-for="(name,key) in palettes" :key="key" :value="key">{{name}}</option></select></label><label>模式<select v-model="mode" aria-label="候选模式"><option value="light">浅色</option><option value="dark">深色</option><option value="system">跟随系统</option></select></label><label>页面<select v-model="view" aria-label="候选页面"><option value="writing">写作工作台（只读）</option><option value="reading">阅读页</option></select></label><label>预览文章<select :value="route.params.id||''" aria-label="候选文章" @change="router.replace('/admin/appearance-lab/'+($event.target as HTMLSelectElement).value)"><option value="">选择已保存文章</option><option v-for="r in records" :key="r.id" :value="r.id">{{r.title}} · {{r.status}}</option></select></label></div></header><p v-if="!route.params.id" class="lab-empty">请选择一篇已保存文章；不会创建演示文章或修改你的内容。</p><section v-else class="lab-projection" aria-label="只读候选预览"><div v-if="view==='writing'" inert><WritePage :key="String(route.params.id)" :preview="appearance"/></div><BlogView v-else embedded :preview="appearance" :target="'/preview/posts/'+route.params.id"/></section></main></template>
