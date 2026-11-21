<script setup lang="ts">
import { ref, computed } from 'vue'
import type { Field } from './types'
import { renderMarkdown } from '../markdown'
const props=defineProps<{field:Field;modelValue:unknown;label:string;disabled?:boolean}>()
const emit=defineEmits<{(event:'update:modelValue',value:unknown):void}>()
const preview=ref(false)
const text=computed(()=>props.modelValue===null||props.modelValue===undefined?'':String(props.modelValue))
const selections=computed(()=>Array.isArray(props.modelValue)?props.modelValue:[])
function change(event:Event){
  const value=(event.target as HTMLInputElement).value
  emit('update:modelValue',value===''?null:props.field.kind==='integer'?Number(value):value)
}
function multiple(event:Event){emit('update:modelValue',Array.from((event.target as HTMLSelectElement).selectedOptions).map(o=>o.value))}
</script>
<template>
  <div class="dynamic-input">
    <template v-if="field.kind==='markdown'">
      <button type="button" class="quiet" :disabled="disabled" @click="preview=!preview">{{preview?'返回字段编辑':'预览字段 Markdown'}}</button>
      <div v-if="preview" class="markdown" v-html="renderMarkdown(text)"></div>
      <label v-else>{{label}}<textarea :value="text" :disabled="disabled" rows="7" maxlength="300000" @input="change" /></label>
    </template>
    <label v-else-if="field.kind==='long_text'">{{label}}<textarea :value="text" :disabled="disabled" rows="5" maxlength="300000" @input="change" /></label>
    <label v-else-if="field.kind==='select'">{{label}}
      <select :aria-label="label" :value="text" :disabled="disabled" @change="change"><option value="">请选择（可留空）</option><option v-for="o in field.rules.options||[]" :key="o.id" :value="o.id" :disabled="!o.active">{{o.label}}{{o.active?'':'（停用）'}}</option></select>
    </label>
    <label v-else-if="field.kind==='multiselect'">{{label}}
      <select :aria-label="label" multiple :value="selections" :disabled="disabled" @change="multiple"><option v-for="o in field.rules.options||[]" :key="o.id" :value="o.id" :disabled="!o.active">{{o.label}}{{o.active?'':'（停用）'}}</option></select>
      <span class="muted">电脑按住Ctrl/Command多选，手机点选。</span>
    </label>
    <label v-else>{{label}}
      <input :value="text" :disabled="disabled" :type="field.kind==='date'?'date':field.kind==='integer'||field.kind==='decimal'?'number':'text'" :step="field.kind==='integer'?'1':field.kind==='decimal'?'0.000001':undefined" :maxlength="field.kind==='short_text'?1000:undefined" @input="change" />
    </label>
  </div>
</template>
