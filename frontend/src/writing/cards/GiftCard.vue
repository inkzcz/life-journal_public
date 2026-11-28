<script setup lang="ts">
import type {Entry} from '../entries'
import EntryCardMedia from './EntryCardMedia.vue'
import EntryCardNotes from './EntryCardNotes.vue'
withDefaults(defineProps<{entry:Entry;heading?:'h2'|'h3'}>(),{heading:'h3'})
</script>
<template><div class="card-split gift-keepsake" :class="{'no-media':!entry.media_ids.length}"><EntryCardMedia v-if="entry.media_ids.length" :ids="entry.media_ids" layout="square"><template #default="media"><slot name="media" v-bind="media"/></template></EntryCardMedia><div class="gift-information"><component :is="heading" class="entry-title">{{entry.name}}</component><p v-if="entry.fields.direction" class="gift-direction">{{entry.fields.direction}}</p><p v-if="entry.fields.person" class="card-subtitle">{{/赠送|送出|送给/.test(entry.fields.direction||'')?'收礼人':/收到|收下/.test(entry.fields.direction||'')?'赠送人':'相关人物'}}：{{entry.fields.person}}</p><p v-if="entry.fields.date||entry.fields.occasion" class="card-subtitle">{{[entry.fields.date,entry.fields.occasion].filter(Boolean).join(' · ')}}</p></div></div><EntryCardNotes :entry="entry" :used="['direction','person','date','occasion']"/></template>
<style scoped>.gift-direction{margin:10px 0 5px;color:var(--ui-accent);font-size:14px}</style>
