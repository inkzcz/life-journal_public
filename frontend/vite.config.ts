import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import {bundledNotices} from './bundled-notices.mjs'
import {createHash} from 'node:crypto'
import {readFileSync} from 'node:fs'
const version=JSON.parse(readFileSync(new URL('./package.json',import.meta.url),'utf8')).version
let info:any={version,short_revision:null,built_at:null,revision_verified:false,source_kind:'unversioned',fingerprint:null}
try{const d=JSON.parse(process.env.LJ_BUILD_INFO||'{}');if(d.version===version&&/^[0-9a-f]{40}$/.test(d.revision)&&/^[0-9a-f]{40}$/.test(d.build_identity)&&typeof d.revision_verified==='boolean'&&((d.revision_source==='git-head'&&d.revision_verified&&d.build_identity===d.revision)||(d.revision_source==='user-provided-zip'&&!d.revision_verified))&&typeof d.built_at==='string'&&d.built_at.endsWith('Z')){info={version,short_revision:d.revision.slice(0,7),built_at:d.built_at,revision_verified:d.revision_verified,source_kind:d.revision_source,fingerprint:createHash('sha256').update(version+'|'+d.revision+'|'+d.build_identity+'|'+(d.revision_verified?'True':'False')).digest('hex')}}}catch{/* direct local development remains explicitly unverified */}

export default defineConfig({
  plugins: [vue(), bundledNotices()],
  define:{__BUILD_INFO__:JSON.stringify(info)},
  server: { host: '127.0.0.1', proxy: { '/api': 'http://127.0.0.1:8000' } },
})
