<script setup lang="ts">
import ModuleIcon from './ModuleIcon.vue'
defineProps<{kind:string;title:string;description:string}>()
</script>
<template><header class="workspace-module-heading"><ModuleIcon :kind="kind"/><div><h2>{{title}}</h2><p>{{description}}</p></div></header></template>
