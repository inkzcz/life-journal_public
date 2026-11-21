<script setup lang="ts">
import {moduleIconPaths as paths} from './iconPaths'
defineProps<{kind:string}>()
</script>
<template><span class="module-icon" aria-hidden="true"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"><path :d="paths[kind]||paths.body"/></svg></span></template>
