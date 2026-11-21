<script setup lang="ts">
import type { Place } from './archive'
defineProps<{value:Partial<Place>}>()
</script>
<template>
<label>地点名称<input v-model="value.name" required maxlength="200" /></label><div class="editor-meta"><label>国家<input v-model="value.country" maxlength="100" /></label><label>地区<input v-model="value.region" maxlength="100" /></label><label>城市<input v-model="value.city" maxlength="100" /></label><label>地点类别<input v-model="value.category" maxlength="100" placeholder="可自由填写" /></label></div>
<label>地址<input v-model="value.address" maxlength="500" /></label><div class="editor-meta"><label>纬度（可选）<input v-model="value.latitude" type="number" min="-90" max="90" step="0.000001" /></label><label>经度（可选）<input v-model="value.longitude" type="number" min="-180" max="180" step="0.000001" /></label></div><p class="muted">经纬度需同时填写，最多6位小数；不会调用地图服务。</p><label>地点备注<textarea v-model="value.notes" maxlength="10000" rows="4" /></label><label class="checks"><input v-model="value.active" type="checkbox" /> 启用地点（停用保留已有引用）</label>
</template>
