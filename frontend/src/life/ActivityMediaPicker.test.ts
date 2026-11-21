// @vitest-environment jsdom
import {createApp,h,ref,nextTick} from 'vue'
import {it,expect,vi} from 'vitest'
import ActivityMediaPicker from './ActivityMediaPicker.vue'
vi.mock('../admin/PrivatePreview.vue',()=>({default:{props:['id','alt'],render(){return h('span','私有缩略图')}}}))
it('filters thumbnails and changes only the association selection',async()=>{
 const selected=ref(['one']),media:any=[{id:'one',asset:{title:'山景',filename:'mountain.jpg',alt:''}},{id:'two',asset:{title:'晚餐',filename:'food.jpg',alt:''}}]
 const root=document.createElement('div');document.body.append(root)
 const app=createApp({render:()=>h(ActivityMediaPicker,{media,modelValue:selected.value,disabled:false,'onUpdate:modelValue':(value:string[])=>selected.value=value})})
 try{app.mount(root);const boxes=root.querySelectorAll<HTMLInputElement>('input[type=checkbox]');expect(boxes).toHaveLength(2);expect(boxes[0]!.checked).toBe(true);boxes[1]!.click();await nextTick();expect(selected.value).toEqual(['one','two']);boxes[0]!.click();await nextTick();expect(selected.value).toEqual(['two']);const search=root.querySelector<HTMLInputElement>('input:not([type=checkbox])')!;search.value='晚餐';search.dispatchEvent(new Event('input',{bubbles:true}));await nextTick();expect(root.querySelectorAll('input[type=checkbox]')).toHaveLength(1);expect(media).toHaveLength(2)}finally{app.unmount();root.remove()}
})
