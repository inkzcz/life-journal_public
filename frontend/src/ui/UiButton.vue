<script setup lang="ts">
withDefaults(defineProps<{variant?:'primary'|'secondary'|'ghost'|'danger';busy?:boolean;disabled?:boolean;type?:'button'|'submit'|'reset'}>(),{variant:'primary',type:'button'})
</script>
<template><button :type="type" class="ui-button" :class="'ui-button--'+variant" :disabled="disabled||busy" :aria-busy="busy||undefined"><slot/><span v-if="busy" role="status">处理中…</span></button></template>
