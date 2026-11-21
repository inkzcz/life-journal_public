<script setup lang="ts">
import {ref,watch,nextTick,onMounted,onUnmounted,useId} from 'vue'
import {useRoute} from 'vue-router'
import {confirmation,finishConfirmation,cancelConfirmations,attachConfirmHost} from './confirm'
const input=ref<HTMLInputElement|null>(null),answer=ref('')
const dialog=ref<HTMLDialogElement|null>(null),cancel=ref<HTMLButtonElement|null>(null),route=useRoute(),id=useId()
let detach:()=>void=()=>{}
onMounted(()=>{detach=attachConfirmHost()});onUnmounted(()=>detach())
watch(()=>route.fullPath,()=>cancelConfirmations())
watch(confirmation,async(value)=>{await nextTick();if(value!==confirmation.value)return;if(value){answer.value=value.initial||'';if(dialog.value&&!dialog.value.open)dialog.value.showModal();if(value.kind==='prompt')input.value?.focus();else cancel.value?.focus()}else if(dialog.value?.open)dialog.value.close()},{flush:'post'})
</script>
<template><Teleport to="body"><dialog ref="dialog" class="ui-confirm" aria-label="确认操作" :aria-describedby="id" @cancel.prevent="finishConfirmation(false)" @close="!dialog?.open&&confirmation&&finishConfirmation(false)"><h2>请确认操作</h2><p :id="id">{{confirmation?.message}}</p><label v-if="confirmation?.kind==='prompt'">确认输入<input ref="input" v-model="answer" aria-label="确认输入" @keydown.enter.prevent="finishConfirmation(answer)"/></label><div class="actions"><button ref="cancel" type="button" class="quiet" @click="finishConfirmation(false)">取消操作</button><button type="button" class="danger" @click="finishConfirmation(confirmation?.kind==='prompt'?answer:true)">确认操作</button></div></dialog></Teleport></template>
