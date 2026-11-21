<script setup lang="ts">
import { ref } from 'vue'
import { useRouter,useRoute } from 'vue-router'
import { request } from '../api'
import ThemeOrnament from './ThemeOrnament.vue'
import {refreshAppearance} from '../ui/theme'
import { safeReturn } from './router'
const props=defineProps<{preview?:boolean}>()
const name=ref(''),password=ref(''),error=ref(''),busy=ref(false),router=useRouter(),route=useRoute()
async function login(){if(props.preview||busy.value)return;if(Array.from(password.value).length>1024){error.value='密码最多1024个字符';return;}busy.value=true;error.value='';try{await request('/auth/login',{method:'POST',body:JSON.stringify({username:name.value,password:password.value})});password.value='';await refreshAppearance();let destination=route.query.return?safeReturn(route.query.return):'/';if(!route.query.return)try{await request('/admin/status');destination='/admin/content'}catch{/* Readers open the private Blog; Admin authorization remains server-side. */}await router.replace(destination)}catch(e){error.value=String(e)}finally{busy.value=false}}
</script>
<template><main class="container auth-page"><header><h1>Life Journal</h1><span class="eyebrow">PRIVATE ARCHIVE</span><ThemeOrnament/></header><section class="login card"><span class="eyebrow">YOUR OWN LITTLE WORLD</span><h2>欢迎回来</h2><p>故事与时光，只留给你信任的人。</p><p v-if="error" class="error" role="alert">{{error}}</p><form @submit.prevent="login"><label>用户名<input v-model="name" required autocomplete="username" maxlength="100" /></label><label>密码<input v-model="password" type="password" required autocomplete="current-password" maxlength="2048" /></label><button :disabled="busy">登录私人空间</button></form></section></main></template>
