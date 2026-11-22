<script setup lang="ts">
import { label as displayLabel,loadText } from '../blog/siteText'
import { onMounted } from 'vue'
onMounted(()=>{void loadText().catch(()=>{})})
import { useRoute } from 'vue-router'
const route=useRoute()
const initialOpen=window.matchMedia('(min-width:761px)').matches
const links=[['/admin/content','内容管理'],['/admin/import','图文导入'],['/admin/ai','AI与写作规则'],['/admin/tags','标签管理'],['/admin/trash','回收站'],['/admin/maintenance','备份与恢复'],['/admin/site','网站设置'],['/admin/system','系统状态'],['/admin/help','使用帮助'],['/','私人 Blog']]
</script>
<template><details class="studio-navigation" :open="initialOpen"><summary>管理导航</summary><nav class="admin-tabs recovery-nav" aria-label="后台导航"><RouterLink v-for="[path,label] in links" :key="path" :to="path" :aria-current="route.path===path?'page':undefined">{{path.startsWith('/admin/')?displayLabel('admin.'+path.split('/').pop(),label):displayLabel('admin.blog',label)}}</RouterLink></nav></details></template>
