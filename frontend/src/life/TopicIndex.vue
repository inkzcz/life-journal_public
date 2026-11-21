<script setup lang="ts">
import {ref,watch} from 'vue'
import {useRoute} from 'vue-router'
import {request} from '../api'
const route=useRoute(),data=ref<any>({items:[],total:0}),page=ref(1),error=ref('')
async function load(){try{data.value=await request('/experiences/'+(route.path==='/trips'?'trips':'places')+'?page='+page.value);error.value=''}catch{error.value='读取失败，请重试'}}
watch(()=>route.path,()=>{page.value=1;void load()},{immediate:true})
</script>
<template><main class="topic-index"><h1>{{route.path==='/trips'?'旅行':'地点足迹'}}</h1><RouterLink to="/">首页</RouterLink><p role="status">{{error}}</p><article v-for="r in data.items" :key="r.id"><template v-if="route.path==='/trips'"><RouterLink :to="'/posts/'+r.id">{{r.title}}</RouterLink><p>{{r.display_date}}</p></template><template v-else><h2>{{r.name}}</h2><p>{{[r.region,r.city].filter(Boolean).join(' · ')}}</p><p v-for="a in r.records" :key="a.id"><RouterLink :to="'/posts/'+a.id">{{a.title}}</RouterLink></p></template></article><p v-if="!data.items.length">暂无已发布内容。</p><div class="actions"><button :disabled="page<=1" @click="page--;load()">上一页</button><button :disabled="page*24>=data.total" @click="page++;load()">下一页</button></div></main></template>
<style scoped>.topic-index{padding:24px;max-width:900px;margin:auto}.topic-index article{border-bottom:1px solid var(--line);padding:16px 0;overflow-wrap:anywhere}</style>
