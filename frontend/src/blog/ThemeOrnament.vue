<script setup lang="ts">
import {inject,type Ref} from 'vue'
import BotanicalIllustration from './BotanicalIllustration.vue'
defineProps<{placement?:'sidebar'|'header'}>()
const candidate=inject<Ref<string>|null>('appearanceCandidate',null)
</script>
<template>
  <div class="theme-ornament" :data-placement="placement||'header'" aria-hidden="true" inert>
    <svg v-if="candidate==='folio'" class="candidate-ornament" viewBox="0 0 180 80" focusable="false"><path class="tone-2" d="M30 22h103v41H30z"/><path class="tone-1" d="M39 16h105v39H39z"/><path class="ornament-line" d="M48 27h44m-44 9h67m-67 9h37M26 65h127"/><path class="tone-4" d="M123 13h12v29l-6-5-6 5Z"/><path class="ornament-line" d="M148 25q15 10 4 22"/></svg>
    <BotanicalIllustration v-else :compact="placement!=='sidebar'" :class="{'candidate-ornament':candidate==='garden'}"/>
  </div>
</template>
