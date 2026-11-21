<script setup lang="ts">
withDefaults(defineProps<{kind?:'loading'|'empty'|'error'|'success';title?:string}>(),{kind:'empty'})
</script>
<template><section :class="kind==='loading'?'ui-loading':kind==='empty'?'ui-empty':'ui-alert--'+kind" :role="kind==='error'?'alert':kind==='loading'||kind==='success'?'status':undefined"><h2 v-if="title">{{title}}</h2><slot/></section></template>
