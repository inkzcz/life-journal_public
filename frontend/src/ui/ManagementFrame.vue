<script setup lang="ts">
import {useId} from 'vue'
import {siteName} from '../blog/siteText'
import AdminNav from '../recovery/AdminNav.vue'
import ThemeOrnament from '../blog/ThemeOrnament.vue'
const props=defineProps<{preview?:boolean}>(),unique=useId(),content=props.preview?'preview-workspace-'+unique:'studio-content'
</script>
<template><div class="studio" :inert="preview||undefined"><a class="studio-skip" :href="'#'+content">跳到管理工作区</a><aside class="studio-sidebar"><RouterLink class="studio-brand" to="/">{{siteName()}} <small>私人生活档案 · 创作空间</small></RouterLink><AdminNav/><ThemeOrnament placement="sidebar"/><p class="studio-caption">记录生活，妥善保存。</p></aside><div :id="content" class="studio-workspace" tabindex="-1"><slot/></div></div></template>
