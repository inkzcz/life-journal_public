<script setup lang="ts">
import {computed} from 'vue'
import {activeAppearance,displayMode} from './theme'
import {appearanceAttrs,colorStyle,customKeys} from '../blog/colors'
import type {Appearance} from '../blog/types'
const props=defineProps<{appearance?:Appearance}>()
const value=computed(()=>props.appearance||activeAppearance.value),mode=computed(()=>displayMode(value.value))
</script>
<template><div class="lj-theme" v-bind="appearanceAttrs(value)" :data-mode="mode" :data-custom="customKeys(value,mode)" :style="colorStyle(value,mode)"><slot/></div></template>
