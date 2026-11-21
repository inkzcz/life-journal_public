<script setup lang="ts">
import {entryNames,entryFields} from '../writing/entries'
import InlineMedia from './InlineMedia.vue'
import {type MediaBlock,type BodyNode} from '../writing/body'
export type RenderedBodyNode=BodyNode&{html?:string;children?:RenderedBodyNode[]}
defineProps<{nodes:RenderedBodyNode[];photos:MediaBlock[]}>()
</script>
<template><template v-for="(node,index) in nodes" :key="index"><section v-if="node.entry" :id="'entry-'+node.entry.id" class="reading-entry"><h3>{{entryNames[node.entry.kind]}} · {{node.entry.name}}</h3><dl><template v-for="[key,label] in entryFields[node.entry.kind]" :key="key"><template v-if="node.entry.fields[key]"><dt>{{label}}</dt><dd>{{node.entry.fields[key]}}</dd></template></template></dl><InlineMedia :images="node.entry.media_ids.map(id=>({id,alt:node.entry!.name,caption:'',width:960,align:'center' as const}))" :photos="photos"/></section><InlineMedia v-else-if="node.media||node.gallery" :images="node.gallery||(node.media?[node.media]:[])" :photos="photos"/><component :is="node.tag" v-else-if="node.tag" :start="node.start"><BodyNodes :nodes="node.children||[]" :photos="photos"/></component><div v-else v-html="node.html"></div></template></template>

<style scoped>.reading-entry{border:1px solid var(--line);padding:16px;margin-block:20px;overflow-wrap:anywhere}.reading-entry img{max-width:100%;max-height:360px}.reading-entry dd{margin:0 0 8px}</style>
