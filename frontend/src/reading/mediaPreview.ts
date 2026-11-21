/** Read-only, authenticated candidate images; never an arbitrary URL resolver. */
import type {ComputedRef,InjectionKey} from 'vue'
export type PreviewImage={id:string;url:string;width?:number;height?:number}
export const readingPreview:InjectionKey<ComputedRef<PreviewImage[]|undefined>>=Symbol('reading-preview')
const uuid='[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}'
const allowed=new RegExp('^/api/(?:admin/exchange/jobs/'+uuid+'/images/'+uuid+'|library-media/'+uuid+'/(?:thumbnail|preview))$')
export function previewImage(images:PreviewImage[]|undefined,id:string){return images?.find(image=>image.id===id&&allowed.test(image.url)&&(image.url.endsWith('/images/'+id)||image.url.includes('/library-media/'+id+'/')))}
