<script setup lang="ts">
import {newId} from '../ids'
import {cityZones,timeZones,validZone} from './zonedTime'
withDefaults(defineProps<{modelValue?:string;label:string;disabled?:boolean}>(),{modelValue:''})
const emit=defineEmits<{(e:'update:modelValue',value:string):void}>(),id='zone-'+newId(),zones=timeZones()
function changed(event:Event){const raw=(event.target as HTMLInputElement).value.trim();let value=raw;if(validZone(raw))value=new Intl.DateTimeFormat('en',{timeZone:raw}).resolvedOptions().timeZone;emit('update:modelValue',value)}
</script>
<template><label class="time-zone-select">{{label}}<input :value="modelValue" :aria-label="label" :list="id" :disabled="disabled" autocomplete="off" placeholder="搜索城市或 IANA 时区" @change="changed"/><datalist :id="id"><option v-for="zone in zones" :key="zone" :value="zone">{{cityZones[zone]||zone.replaceAll('_',' ')}}</option></datalist></label></template>
<style scoped>.time-zone-select{display:block;min-width:0}.time-zone-select input{width:100%;max-width:100%;box-sizing:border-box}</style>
