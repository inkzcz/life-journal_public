<script setup lang="ts">
import type {Entry} from '../entries'
import EntryCardNotes from './EntryCardNotes.vue'
defineProps<{entry:Entry}>()
</script>
<template><p v-if="entry.fields.region||entry.fields.city||entry.fields.address||entry.fields.date" class="location-line card-subtitle"><span>{{[entry.fields.region,entry.fields.city,entry.fields.address].filter(Boolean).join(' · ')}}</span><time v-if="entry.fields.date">{{entry.fields.date}}</time></p><EntryCardNotes :entry="entry" :used="['date','region','city','address']"/></template>
<style scoped>.location-line{display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px 20px;margin-top:12px}</style>
