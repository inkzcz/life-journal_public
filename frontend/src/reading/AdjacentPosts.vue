<script setup lang="ts">
import PrivatePreview from '../admin/PrivatePreview.vue'
export type Neighbor={id:string;title:string;display_date:string;cover:{id:string;alt:string}|null}
defineProps<{data:{previous:Neighbor|null;next:Neighbor|null}}>()
const emit=defineEmits<{(e:'navigate',path:string):void}>()
</script>
<template><nav v-if="data.previous||data.next" class="adjacent-posts" aria-label="全站相邻文章"><p>继续翻阅 <small>全站已发布故事 · 展示日期从近到远</small></p><div><template v-for="(label,key) in {previous:'上一篇',next:'下一篇'}" :key="key"><a v-if="data[key]" :href="'/posts/'+data[key]!.id" @click.prevent="emit('navigate','/posts/'+data[key]!.id)"><PrivatePreview v-if="data[key]!.cover" :id="data[key]!.cover!.id" :alt="data[key]!.cover!.alt"/><span><small>{{label}} · {{data[key]!.display_date}}</small><strong>{{data[key]!.title}}</strong><span aria-hidden="true">{{key==='previous'?'←':'→'}}</span></span></a></template></div></nav></template>
