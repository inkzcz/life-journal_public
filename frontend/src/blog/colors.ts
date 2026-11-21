import type { Appearance,Style,PaletteName } from './types'
export const colorLabels={page_background:'页面背景',card_background:'内容卡片背景',body_text:'正文文字',heading_text:'标题',muted_text:'次要文字',nav_background:'导航栏背景',nav_text:'导航栏文字',link:'普通链接',primary_background:'主要按钮背景',primary_text:'主要按钮文字',secondary_background:'次要按钮背景',secondary_text:'次要按钮文字',tag_background:'标签背景',tag_text:'标签文字',border:'边框与分隔线',accent:'强调色'} as const
export type ColorKey=keyof typeof colorLabels
export type Theme='modern'|'default'|'editorial'|'soft'|'glass'|'celadon'
export type ColorMode='light'|'dark'
export type Palette=Partial<Record<ColorKey,string>>
export type ColorOverrides=Partial<Record<Theme,Partial<Record<ColorMode,Palette>>>>
export const isHex=(value:unknown):value is string=>typeof value==='string'&&value.length===7&&/^#[\da-f]{6}$/i.test(value)
export type CombinationColors=Partial<Record<Style,Partial<Record<PaletteName,Partial<Record<ColorMode,Palette>>>>>>
export function resolvedStyle(a:Appearance):Style{return a.style||({modern:'modern-flat',default:'modern-flat',editorial:'editorial',soft:'modern-soft',glass:'glass',celadon:'modern-soft'} as const)[a.theme]||'modern-flat'}
export function originPalette(a:Appearance):PaletteName{return a.theme==='soft'?'lilac':'celadon'}
export function appearanceAttrs(a:Appearance){return {'data-theme':a.theme==='default'?'modern':a.theme,'data-style':resolvedStyle(a),'data-palette':a.palette||'legacy','data-appearance':a.style||a.palette?'split':'legacy'}}
export function effectiveColors(a:Appearance,mode:ColorMode):Palette{
 if(a.palette){const own=a.combination_colors?.[resolvedStyle(a)]?.[a.palette];if(own&&Object.hasOwn(own,mode))return own[mode]||{}
  if(resolvedStyle(a)!==resolvedStyle({...a,style:null})||a.palette!==originPalette(a))return {}
 }
 return a.colors?.[a.theme]?.[mode]||{}
}
export function withColors(a:Appearance,mode:ColorMode,p:Palette):Appearance{
 if(!a.palette)return {...a,colors:{...a.colors,[a.theme]:{...a.colors?.[a.theme],[mode]:p}}}
 const style=resolvedStyle(a);return {...a,combination_colors:{...a.combination_colors,[style]:{...a.combination_colors?.[style],[a.palette]:{...a.combination_colors?.[style]?.[a.palette],[mode]:p}}}}
}
export function clearColors(a:Appearance):Appearance{
 if(a.palette)return withColors(withColors(a,'light',{}),'dark',{})
 const colors={...a.colors};delete colors[a.theme];return {...a,colors}
}
// Only fixed property names and six-digit HEX values become inline styles.
export function colorStyle(a:Appearance,mode:ColorMode){const p=effectiveColors(a,mode);return Object.fromEntries((Object.keys(colorLabels) as ColorKey[]).filter(k=>isHex(p[k])).map(k=>['--reader-'+k.replaceAll('_','-'),p[k]!]))}
export function customKeys(a:Appearance,mode:ColorMode){return Object.keys(colorLabels).filter(k=>isHex(effectiveColors(a,mode)[k as ColorKey])).join(' ')}
export function contrast(a:string,b:string){const luminance=(s:string)=>{const channels=[1,3,5].map(i=>parseInt(s.slice(i,i+2),16)/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4);return .2126*channels[0]!+.7152*channels[1]!+.0722*channels[2]!};if(!isHex(a)||!isHex(b))return 0;const x=luminance(a),y=luminance(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05)}
