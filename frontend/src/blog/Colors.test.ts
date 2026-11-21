import { describe,it,expect } from 'vitest'
import { contrast,isHex,colorStyle,customKeys,colorLabels } from './colors'
import type { Appearance } from './types'
describe('reader-only finite color configuration',()=>{
 it('accepts six-digit colors and rejects CSS, alpha, whitespace and active content',()=>{
  for(const value of ['#123456','#AbCdEf'])expect(isHex(value)).toBe(true)
  for(const value of ['red','#fff','#12345678',' #123456','#123456\n','url(x)','var(--ink)','</style>',null,1])expect(isHex(value)).toBe(false)
 })
 it('uses separate themes and modes and keeps inheritance empty',()=>{
  const a:Appearance={theme:'modern',mode:'system',colors:{modern:{light:{body_text:'#123456'},dark:{body_text:'#fedcba'}},glass:{light:{page_background:'#eeeeee'}}}}
  expect(colorStyle(a,'light')).toEqual({'--reader-body-text':'#123456'})
  expect(colorStyle(a,'dark')).toEqual({'--reader-body-text':'#fedcba'})
  expect(colorStyle({...a,theme:'glass'},'dark')).toEqual({})
  expect(colorStyle({theme:'soft',mode:'system'},'light')).toEqual({})
  expect(customKeys(a,'light')).toBe('body_text')
 })
 it('never turns unknown keys or invalid legacy values into styles',()=>{
  const a={theme:'modern',mode:'light',colors:{modern:{light:{body_text:'url(evil)',position:'#123456',link:'#123456'}}}} as unknown as Appearance
  expect(colorStyle(a,'light')).toEqual({'--reader-link':'#123456'})
  expect(customKeys(a,'light')).toBe('link');expect(Object.keys(colorLabels)).toHaveLength(16)
 })
 it('calculates WCAG luminance contrast instead of raw RGB distance',()=>{
  expect(contrast('#000000','#ffffff')).toBe(21)
  expect(contrast('#ffffff','#ffffff')).toBe(1)
  expect(contrast('#777777','#ffffff')).toBeCloseTo(4.478,2)
  expect(contrast('#24332e','#f7f6f2')).toBeGreaterThan(4.5)
 })
})
it('isolates new celadon colors from stable legacy soft colors',()=>{
 const a:Appearance={theme:'soft',mode:'system',colors:{soft:{light:{accent:'#65479a'}},celadon:{light:{accent:'#327b74'}}}}
 expect(colorStyle(a,'light')).toEqual({'--reader-accent':'#65479a'})
 expect(colorStyle({...a,theme:'celadon'},'light')).toEqual({'--reader-accent':'#327b74'})
 expect(a.colors?.soft?.light?.accent).toBe('#65479a')
})
it('keeps style and palette independent and resets without deleting archived overrides',async()=>{
 const {resolvedStyle,appearanceAttrs,effectiveColors,withColors,clearColors}=await import('./colors')
 const legacy:Appearance={theme:'soft',mode:'system',colors:{soft:{light:{accent:'#65479a'}}}}
 expect(appearanceAttrs(legacy)).toEqual({'data-theme':'soft','data-style':'modern-soft','data-palette':'legacy','data-appearance':'legacy'})
 const mapped:Appearance={...legacy,style:'modern-soft',palette:'lilac'}
 expect(effectiveColors(mapped,'light').accent).toBe('#65479a')
 const updated=withColors(mapped,'light',{body_text:'#123456'})
 expect(effectiveColors(updated,'light')).toEqual({body_text:'#123456'})
 expect(effectiveColors({...updated,style:'glass'},'light')).toEqual({})
 expect(effectiveColors({...updated,palette:'celadon'},'light')).toEqual({})
 expect(updated.palette).toBe('lilac');expect(resolvedStyle(updated)).toBe('modern-soft')
 const reset=clearColors(mapped)
 expect(effectiveColors(reset,'light')).toEqual({});expect(reset.colors).toEqual(legacy.colors)
 expect(legacy.combination_colors).toBeUndefined()
})
it('preserves all six legacy identities and modes as a distinct compatibility path',async()=>{
 const {appearanceAttrs}=await import('./colors')
 for(const [theme,style] of [['modern','modern-flat'],['default','modern-flat'],['editorial','editorial'],['glass','glass'],['soft','modern-soft'],['celadon','modern-soft']] as const){
  expect(appearanceAttrs({theme,mode:'dark'})).toEqual({'data-theme':theme==='default'?'modern':theme,'data-style':style,'data-palette':'legacy','data-appearance':'legacy'})
 }
})
