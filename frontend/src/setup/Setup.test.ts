// @vitest-environment jsdom
import { describe,it,expect } from 'vitest'
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'
import HelpPage from './HelpPage.vue'
import { applyText,label } from '../blog/siteText'
describe('Phase4A display-only text and help',()=>{
 it('retains configured page defaults and handles override reset',()=>{
  applyText({values:{'nav.home':'我的家'},defaults:{'nav.home':'首页','home.welcome':'系统默认'}})
  expect(label('nav.home','首页')).toBe('我的家')
  expect(label('home.welcome','用户原有首页标题')).toBe('用户原有首页标题')
  applyText({values:{},defaults:{'nav.home':'首页'}})
  expect(label('nav.home','首页')).toBe('首页')
 })
 it('documents external HDD responsibility without promising validation',async()=>{
  const html=await renderToString(createSSRApp(HelpPage))
  expect(html).toContain('Life Journal 无法验证该外部任务成功')
  expect(html).toContain('至少8个字符')
  expect(html).toContain('不删除卷')
 })
})

import { passwordError } from './passwordPolicy'
it('counts Unicode code points and does not impose composition rules',()=>{
 expect(passwordError('QuietFox')).toBe('')
 expect(passwordError('😀😇😂🙃🙂😎😊🤓')).toBe('')
 expect(passwordError('😀😇😂🙃'.repeat(257))).not.toBe('')
 expect(passwordError('七个汉字不足够')).not.toBe('')
 expect(passwordError('生活里值得收藏的片刻')).toBe('')
 expect(passwordError('aaaaaaaa')).not.toBe('')
})
