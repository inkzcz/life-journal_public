<script setup lang="ts">
import type {Entry} from '../entries'
import EntryCardNotes from './EntryCardNotes.vue'
defineProps<{entry:Entry}>()
</script>
<template><p v-if="entry.fields.performer" class="show-performer">{{entry.fields.performer}}</p><p v-if="entry.fields.show_type||entry.fields.venue" class="card-subtitle"><span aria-hidden="true">{{/音乐剧|话剧|戏剧/.test(entry.fields.show_type||'')?'◈':'♫'}}</span> {{[entry.fields.show_type,entry.fields.venue].filter(Boolean).join(' · ')}}</p><dl v-if="['date','time','seat','ticket_tier','end_time'].some(k=>entry.fields[k])" class="card-pills ticket-perforation"><template v-for="[key,label] in [['date','演出日期'],['time','开场时间'],['seat','座位'],['ticket_tier','票档'],['end_time','结束时间']]" :key="key"><div v-if="entry.fields[key!]?.trim()"><dt>{{label}}</dt><dd>{{entry.fields[key!]}}</dd></div></template></dl><EntryCardNotes :entry="entry" :used="['show_type','performer','date','time','venue','seat','ticket_tier','end_time']"/></template>
<style scoped>.show-performer{font-size:18px;margin:8px 0;line-height:1.5}</style>
