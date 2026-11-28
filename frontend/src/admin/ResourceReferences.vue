<script setup lang="ts">
import {computed} from 'vue'
import type {RecordRef} from './archive'
const props=defineProps<{references:RecordRef[];disabled?:boolean}>()
const emit=defineEmits<{(e:'record',id:string):void}>()
const categories=[['current','当前有效引用'],['history','历史版本引用'],['inactive','已失效索引'],['trash','回收站引用'],['system','其他保护引用']] as const
const groups=computed(()=>categories.map(([key,label])=>{const rows=props.references.filter(r=>(r.category||'system')===key);return {key,label,rows,count:new Set(rows.map(r=>r.id+':'+(r.revision||''))).size}}))
</script>
<template><section><h4>资源引用</h4><p v-if="!groups[0]?.count&&references.length" class="muted">当前正文已不再使用此资源，但仍存在历史版本、回收站或保留身份引用。</p><details v-for="group in groups" :key="group.key"><summary>{{group.label}}：{{group.count}}</summary><p v-if="!group.rows.length" class="muted">暂无此类引用</p><button v-for="(r,i) in group.rows" :key="r.id+'-'+r.kind+'-'+r.revision+'-'+i" class="entry" :disabled="disabled||r.deleted||r.category==='system'" @click="emit('record',r.id)">{{r.kind||'记录'}} · {{r.title}}{{r.revision?' · 修订'+r.revision:''}}{{r.deleted?'（文章在回收站）':''}}{{r.category==='inactive'?'（已失效，保留身份）':''}}</button></details></section></template>
