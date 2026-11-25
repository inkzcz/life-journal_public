<script setup lang="ts">
import {computed} from 'vue'
import type {Entry} from './entries'
import EntryCardShell from './cards/EntryCardShell.vue'
import EntryCardMedia from './cards/EntryCardMedia.vue'
import LocationCard from './cards/LocationCard.vue'
import FoodCard from './cards/FoodCard.vue'
import MovieCard from './cards/MovieCard.vue'
import ShowCard from './cards/ShowCard.vue'
import GiftCard from './cards/GiftCard.vue'
import TransportCard from './cards/TransportCard.vue'
const props=withDefaults(defineProps<{entry:Entry;heading?:'h2'|'h3'}>(),{heading:'h3'})
const layouts={l:LocationCard,f:FoodCard,m:MovieCard,s:ShowCard,g:GiftCard,t:TransportCard}
const cover=computed(()=>['l','s'].includes(props.entry.kind)&&!!props.entry.media_ids.length)
</script>
<template><EntryCardShell :entry="entry" :heading="heading" :body-title="['f','m','g'].includes(entry.kind)"><template v-if="cover&&$slots.media" #cover><EntryCardMedia :ids="entry.media_ids" layout="cover"><template #default="media"><slot name="media" v-bind="media"/></template></EntryCardMedia></template><template v-if="$slots.actions" #actions><slot name="actions"/></template><component :is="layouts[entry.kind]" :entry="entry" :heading="heading"><template v-if="$slots.media" #media="media"><slot name="media" v-bind="media"/></template></component><template v-if="$slots.footer" #footer><slot name="footer"/></template></EntryCardShell></template>
