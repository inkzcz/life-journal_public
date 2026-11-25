<script setup lang="ts">
import {ref,watch} from 'vue'
import {useRoute} from 'vue-router'
import {request} from '../api'
import {entryNames,type EntryKind} from '../writing/entries'
import EntryCard from '../writing/EntryCard.vue'
import PrivatePreview from '../admin/PrivatePreview.vue'
const route=useRoute(),data=ref<any>({items:[],total:0}),page=ref(1),filter=ref(''),error=ref('')
const kind=()=>route.params.kind as EntryKind
async function load(){try{data.value=await request('/experiences?kind='+kind()+'&page='+page.value+'&transport_type='+encodeURIComponent(filter.value));error.value=''}catch{error.value='无法读取专题，请重试'}}
watch(()=>route.params.kind,()=>{page.value=1;filter.value='';void load()},{immediate:true})
</script>
<template><main class="experience-page"><RouterLink to="/">返回首页</RouterLink><h1>{{entryNames[kind()]||'经历'}}记录</h1><p>来自文章正文的记录，照片复用原媒体。</p><form v-if="kind()==='t'" @submit.prevent="page=1;load()"><label>交通类型筛选<input v-model="filter" maxlength="100"/></label><button>筛选</button></form><p role="status">{{error}}</p><EntryCard v-for="e in data.items" :key="e.record_id+e.id" :entry="e" heading="h2"><template #media><div class="entry-thumbnails"><PrivatePreview v-for="id in e.media_ids" :key="id" :id="id" :alt="e.name"/></div></template><template #footer><RouterLink :to="'/posts/'+e.record_id+'#'+e.anchor">来源：{{e.record_title}}</RouterLink></template></EntryCard><p v-if="!data.items.length">暂无已发布记录。</p><div class="actions"><button :disabled="page<=1" @click="page--;load()">上一页</button><span>{{page}}</span><button :disabled="page*24>=data.total" @click="page++;load()">下一页</button></div></main></template>
<style scoped>.experience-page{max-width:900px;margin:auto;padding:24px;min-width:0}.experience-topic{padding:20px 0;border-bottom:1px solid var(--line);overflow-wrap:anywhere}.experience-topic dd{margin:0 0 8px}.topic-photos{display:flex;flex-wrap:wrap;gap:8px}.topic-photos img{width:min(200px,100%);height:auto;object-fit:contain}</style>
