<script setup lang="ts">
defineProps<{title?:string}>()
</script>
<template><section class="ui-panel"><header v-if="title" class="ui-section-header"><h2>{{title}}</h2><slot name="actions"/></header><slot/></section></template>
