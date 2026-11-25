<script setup lang="ts">
import type {Entry} from '../entries'
import EntryCardMedia from './EntryCardMedia.vue'
import EntryCardNotes from './EntryCardNotes.vue'
withDefaults(defineProps<{entry:Entry;heading?:'h2'|'h3'}>(),{heading:'h3'})
</script>
<template><div class="card-split food-meal" :class="{'no-media':!entry.media_ids.length}"><EntryCardMedia v-if="entry.media_ids.length" :ids="entry.media_ids" layout="square"><template #default="media"><slot name="media" v-bind="media"/></template></EntryCardMedia><div class="meal-information"><component :is="heading" class="entry-title">{{entry.name}}</component><p v-if="entry.fields.rating" class="card-rating">{{entry.fields.rating}}<small v-if="entry.fields.rating_scale==='5'"> / 5</small></p><p v-if="entry.fields.restaurant_location" class="card-subtitle">{{entry.fields.restaurant_location}}</p><p v-if="entry.fields.date||entry.fields.meal_period" class="card-subtitle">{{[entry.fields.date,entry.fields.meal_period].filter(Boolean).join(' · ')}}</p><p v-if="entry.fields.price_per_person" class="card-subtitle">人均 {{entry.fields.currency}} {{entry.fields.price_per_person}}</p></div></div><EntryCardNotes :entry="entry" :used="['rating','rating_scale','restaurant_location','date','meal_period','price_per_person','currency']"/></template>
