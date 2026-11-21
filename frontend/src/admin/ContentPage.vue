<script setup lang="ts">
import { useRouter } from 'vue-router'
import AdminContent from './AdminContent.vue'
defineProps<{previewOnly?:boolean}>()
const router=useRouter()
</script>
<template><main class="container"><AdminContent :preview-only="previewOnly" @exit="router.push('/')" /></main></template>
