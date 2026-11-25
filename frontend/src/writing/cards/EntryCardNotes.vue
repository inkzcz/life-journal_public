<script setup lang="ts">
import {computed} from 'vue'
import type {Entry} from '../entries'
import {extras} from './cardFields'
const props=defineProps<{entry:Entry;used:string[]}>()
const more=computed(()=>extras(props.entry,[...props.used,'description','review']))
</script>
<template><template v-for="key in ['review','description']" :key="key"><section v-if="entry.fields[key]?.trim()" class="entry-reflection"><h4>{{key==='review'?'感受':'备注与回忆'}}</h4><p>{{entry.fields[key]}}</p></section></template><details v-if="more.length" class="entry-extra"><summary>补充信息（{{more.length}}）</summary><dl class="entry-details card-pills"><div v-for="item in more" :key="item.key"><dt>{{item.label}}</dt><dd>{{item.value}}</dd></div></dl></details></template>
<style scoped>.entry-reflection{margin-top:16px;padding-top:12px;border-top:1px solid var(--ui-line)}.entry-reflection h4{font-size:12px;font-weight:500;color:var(--ui-muted);margin:0 0 6px}.entry-reflection p{font-size:14px;line-height:1.8;white-space:pre-line;margin:0}.entry-extra{margin-top:14px;font-size:12px;color:var(--ui-muted)}.entry-extra dd{color:var(--ui-ink)}.entry-reflection[style*="display: none"]{margin:0;padding:0;border:0}</style>
