<script setup lang="ts">
import { computed, onMounted, onUnmounted,watch } from 'vue'
import ThemeBoundary from '../ui/ThemeBoundary.vue'
import {refreshAppearance} from '../ui/theme'
import ManagementFrame from '../ui/ManagementFrame.vue'
import ConfirmHost from '../ui/ConfirmHost.vue'
import { useRoute, useRouter } from 'vue-router'
import { siteName } from './siteText'
import AdminNav from '../recovery/AdminNav.vue'
const router=useRouter(),route=useRoute()
function refreshPrivateTheme(){if(route.path!=='/login'&&route.path!=='/setup')void refreshAppearance()}
watch(()=>route.path,refreshPrivateTheme)
onMounted(()=>{void router.isReady().then(refreshPrivateTheme)})
const studio=computed(()=>route.path.startsWith('/admin/'))
function expired(event:Event){queueMicrotask(()=>{if(!event.defaultPrevented&&router.currentRoute.value.path!=='/login')void router.replace({path:'/login',query:{return:router.currentRoute.value.fullPath}})})}
onMounted(()=>window.addEventListener('session-expired',expired));onUnmounted(()=>window.removeEventListener('session-expired',expired))
</script>
<template><ThemeBoundary class="app-theme"><ManagementFrame v-if="studio"><RouterView/></ManagementFrame><RouterView v-else/><ConfirmHost/></ThemeBoundary></template>
