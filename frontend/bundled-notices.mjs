// Original build tooling. Preserve upstream notices verbatim, without executing packages.
import {readFileSync, readdirSync, existsSync, realpathSync} from 'node:fs'
import {dirname, join, relative, resolve, basename} from 'node:path'
import {createHash} from 'node:crypto'

const noticeName = /^(licen[cs]e|copying|copyright|notice|authors)([._-].*)?$/i
const sha256 = text => createHash('sha256').update(text).digest('hex')

export function collectNotices(ids, root) {
  root = realpathSync(root)
  const packages = new Map()
  for (const id of ids) {
    const clean = id.split('?')[0]
    if (!clean.includes('/node_modules/') || clean.startsWith('\0')) continue
    let directory = dirname(realpathSync(clean))
    while (!existsSync(join(directory, 'package.json'))) {
      const parent = dirname(directory)
      if (parent === directory || !directory.startsWith(root + '/')) throw Error('Unresolved bundled package')
      directory = parent
    }
    if (!directory.startsWith(root + '/node_modules/')) throw Error('Bundled dependency outside approved root')
    const pkg = JSON.parse(readFileSync(join(directory, 'package.json'), 'utf8'))
    const key = relative(root, directory).replaceAll('\\', '/')
    if (packages.has(key)) continue
    const notices = readdirSync(directory).filter(name => noticeName.test(name)).sort().map(name => {
      const path = join(directory, name)
      if (!realpathSync(path).startsWith(directory + '/')) throw Error('External notice link')
      const raw = readFileSync(path)
      if (raw.length > 2 * 1024 * 1024 || raw.includes(0)) throw Error('Unsupported notice content')
      const text = new TextDecoder('utf-8', {fatal: true, ignoreBOM: true}).decode(raw)
      return {name, sha256: sha256(raw), text}
    })
    if (!notices.length) throw Error('No notice for bundled package: ' + pkg.name)
    packages.set(key, {path: key, name: pkg.name, version: pkg.version, license_declared: pkg.license ?? null, notices})
  }
  return [...packages.values()].sort((a, b) => a.path < b.path ? -1 : a.path > b.path ? 1 : 0)
}

export function bundledNotices() {
  let root
  return {
    name: 'life-journal-bundled-notices', apply: 'build',
    configResolved(config) { root = resolve(config.root) },
    generateBundle(_options, bundle) {
      const ids = Object.values(bundle).filter(item => item.type === 'chunk').flatMap(item => Object.keys(item.modules))
      const packages = collectNotices(ids, root)
      if (!packages.length) throw Error('Expected bundled dependencies')
      const overview = {
        format: 'life-journal-browser-notices-v1',
        scope: 'Packages with modules in emitted Rollup chunks; not every lockfile or development dependency',
        third_party_relicensed: false,
        packages,
      }
      this.emitFile({type: 'asset', fileName: 'legal/browser-notices.json', source: JSON.stringify(overview, null, 2) + '\n'})
      const text = packages.map(pkg => pkg.name + '@' + pkg.version + '\n' + pkg.notices.map(n => '--- ' + basename(n.name) + ' ---\n' + n.text).join('\n')).join('\n\n')
      this.emitFile({type: 'asset', fileName: 'legal/THIRD_PARTY_NOTICES.txt', source: text + '\n'})
    },
  }
}
