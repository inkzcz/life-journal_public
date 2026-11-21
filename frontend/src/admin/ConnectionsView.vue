<script setup lang="ts">
import type { Connections } from './archive'
import PrivatePreview from './PrivatePreview.vue'
defineProps<{value:Connections}>();defineEmits<{(e:'record',id:string):void}>()
</script>
<template><section class="connections-view"><h3 v-if="value.media.length">照片</h3><div class="attached-grid"><figure v-for="m in value.media" :key="m.id"><a :href="'/api/library-media/'+m.id+'/preview'" target="_blank" rel="noopener"><PrivatePreview :id="m.id" :alt="m.asset.alt" /></a><figcaption>{{m.cover?'封面 · ':''}}{{m.caption||m.asset.title||m.asset.filename}}</figcaption></figure></div>
<section v-if="value.links.length"><h3>相关内容 · 从本篇指向</h3><button v-for="l in value.links" :key="l.id+l.label" class="entry" :disabled="l.deleted" @click="$emit('record',l.id)">{{l.label}} → {{l.title}}{{l.deleted?'（已删除，历史引用保留）':''}}</button></section>
<section v-if="value.incoming.length"><h3>引用本篇的内容</h3><button v-for="l in value.incoming" :key="l.id+l.label" class="entry" :disabled="l.deleted" @click="$emit('record',l.id)">{{l.title}} → {{l.label}}{{l.deleted?'（已删除，历史引用保留）':''}}</button></section>
<section v-if="value.places.length"><h3>地点</h3><article v-for="p in value.places" :key="p.id" class="linked-item"><strong>{{p.name}}{{p.active?'':'（已停用）'}}</strong><p>{{[p.country,p.region,p.city,p.address].filter(Boolean).join(' · ')}}</p><p class="muted">{{p.category}} {{p.latitude!==null?'· '+p.latitude+', '+p.longitude:''}}</p><p class="plain-value">{{p.notes}}</p></article></section></section></template>
