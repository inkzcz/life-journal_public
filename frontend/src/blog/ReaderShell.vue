<script setup lang="ts">
import {activeAppearance,systemDark,rememberAppearance,appearanceEpoch} from '../ui/theme'
import ThemeOrnament from './ThemeOrnament.vue'
import {ref,computed,onMounted,onUnmounted} from 'vue'
import {request} from '../api'
import {blankSite,type Site} from './types'
import {colorStyle,customKeys,appearanceAttrs} from './colors'
const site=ref<Site>(blankSite())
const dark=computed(()=>activeAppearance.value.mode==='dark'||activeAppearance.value.mode==='system'&&systemDark.value)
let alive=true;onUnmounted(()=>{alive=false})
onMounted(async()=>{try{const epoch=appearanceEpoch();const result=await request('/blog/site');if(!alive)return;site.value=result;rememberAppearance(site.value.appearance,epoch)}catch{/* private guard remains authoritative */}})
</script>
<template><main class="blog lj-theme reader-archive" v-bind="appearanceAttrs(activeAppearance)" :data-mode="dark?'dark':'light'" :data-custom="customKeys(activeAppearance,dark?'dark':'light')" :style="colorStyle(activeAppearance,dark?'dark':'light')"><header><RouterLink to="/">{{site.title}}</RouterLink><nav aria-label="生活档案"><RouterLink to="/stories">故事</RouterLink><RouterLink to="/food">美食足迹</RouterLink><RouterLink to="/about">关于本站</RouterLink><slot name="nav"/></nav></header><ThemeOrnament/><section class="archive-content"><slot/></section></main></template>
<style scoped>.reader-archive{min-height:100vh;background:var(--paper,var(--ui-card));color:var(--ink,var(--ui-ink))}header{max-width:1100px;margin:auto;padding:20px;display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap}nav{display:flex;gap:16px;flex-wrap:wrap}.archive-content{max-width:1000px;margin:auto;padding:24px 20px 80px;min-width:0}.archive-content :deep(input),.archive-content :deep(select){max-width:100%;box-sizing:border-box}.archive-content :deep(.filters){display:flex;gap:12px;flex-wrap:wrap;align-items:end}.archive-content :deep(.archive-row){padding:20px 0;border-bottom:1px solid var(--line,var(--ui-line));overflow-wrap:anywhere}.archive-content :deep(.actions){display:flex;gap:10px;flex-wrap:wrap}.archive-content :deep(button){min-height:40px}@media(max-width:420px){.archive-content{padding:16px 12px 60px}.archive-content :deep(.filters)>label{width:100%}}</style>
