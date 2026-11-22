// Invoked explicitly by node --test; kept outside Vitest's suite pattern.
import test from 'node:test'
import assert from 'node:assert/strict'
import {mkdtempSync, mkdirSync, writeFileSync, rmSync, symlinkSync} from 'node:fs'
import {join} from 'node:path'
import {tmpdir} from 'node:os'
import {collectNotices} from './bundled-notices.mjs'

test('Actual emitted packages retain exact notices, omit unbundled tools and deduplicate modules', () => {
  const root = mkdtempSync(join(tmpdir(), 'lj-notices-'))
  try {
    const pkg = join(root, 'node_modules', 'synthetic')
    mkdirSync(pkg, {recursive: true})
    writeFileSync(join(pkg, 'package.json'), JSON.stringify({name: 'synthetic', version: '1', license: 'MIT'}))
    writeFileSync(join(pkg, 'one.js'), 'synthetic fixture')
    writeFileSync(join(pkg, 'LICENSE'), '\ufeffSynthetic upstream notice 中文\r\n')
    const result = collectNotices([join(pkg, 'one.js'), join(pkg, 'one.js') + '?test'], root)
    assert.equal(result.length, 1)
    assert.equal(result[0].notices[0].text, '\ufeffSynthetic upstream notice 中文\r\n')
    assert.equal(result[0].path, 'node_modules/synthetic')
    rmSync(join(pkg, 'LICENSE'))
    assert.throws(() => collectNotices([join(pkg, 'one.js')], root), /No notice/)
    symlinkSync(join(root, 'outside.txt'), join(pkg, 'LICENSE'))
    writeFileSync(join(root, 'outside.txt'), 'Outside fixture')
    assert.throws(() => collectNotices([join(pkg, 'one.js')], root), /External notice/)
  } finally { rmSync(root, {recursive: true, force: true}) }
})
