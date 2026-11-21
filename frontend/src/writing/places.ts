import { marked } from 'marked'
import {placeToken,placeStart} from './placeSyntax'
const labels:Record<string,string>={l:'地点',f:'美食',s:'景点',h:'住宿',t:'交通',c:'咖啡',p:'购物'}
import {placeIconPaths as paths} from './iconPaths'
const escape=(s:string)=>s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!))
marked.use({extensions:[{name:'placeMark',level:'inline',start:placeStart,tokenizer(src){const token=placeToken(src);if(token)return {type:'placeMark',...token}},renderer(token){return `<span class="lj-place-mark" data-mark-kind="${token.kind}" title="${labels[token.kind]}">${escape(token.name)}</span>`}}]})
export function decoratePlaces(template:HTMLTemplateElement){
 template.content.querySelectorAll<HTMLElement>('.lj-place-mark[data-mark-kind]').forEach(el=>{const kind=el.dataset.markKind||'';if(!paths[kind])return;const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('width','18');svg.setAttribute('height','18');svg.setAttribute('fill','none');svg.setAttribute('stroke','currentColor');svg.setAttribute('stroke-width','1.7');svg.setAttribute('aria-hidden','true');const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',paths[kind]!);svg.append(path);el.prepend(svg)})
}
export const placeKinds=Object.entries(labels).map(([kind,label])=>({kind,label}))
