// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'
import { renderMarkdown } from './markdown'

describe('private Markdown preview', () => {
  it('renders headings, lists and emphasis', () => {
    const html = renderMarkdown('# 日记\n\n**生活**\n\n- 照片')
    expect(html).toContain('<h1>日记</h1>')
    expect(html).toContain('<strong>生活</strong>')
    expect(html).toContain('<li>照片</li>')
  })
  it('removes executable markup and remote tracking images', () => {
    const html = renderMarkdown('<script>alert(1)</script><img src="https://example.com/pixel" onerror="alert(1)">[坏链接](javascript:alert(1))')
    expect(html).not.toMatch(/<script|<img|onerror|href="javascript:/)
  })
})
