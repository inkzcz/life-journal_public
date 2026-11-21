import { reactive } from 'vue'

export type SaveMode = 'auto' | 'manual' | 'preview'
export type SaveStatus = 'unchanged' | 'dirty' | 'waiting' | 'saving' | 'saved' | 'error' | 'conflict' | 'blocked'
type Options<T> = {
  snapshot: () => string
  enabled: () => boolean
  identity: () => string | undefined
  blocked: () => string
  persist: (snapshot: string, revision: number, signal: AbortSignal) => Promise<T>
  accept: (result: T, sent: string) => { snapshot: string; revision: number }
  delay?: number
  timeout?: number
}

// One editor session owns one confirmed snapshot and at most one request.
// No content is written to localStorage, URLs or background unload requests.
export function createSaveSession<T>(options: Options<T>) {
  const state = reactive({ status: 'unchanged' as SaveStatus, confirmed: '', revision: 0,
    saving: false, paused: false, message: '', code: 0, completedAt: '', uncertainCreation: false })
  let generation = 0, disposed = false
  let timer: ReturnType<typeof setTimeout> | undefined
  let controller: AbortController | undefined
  const cancelTimer = () => { clearTimeout(timer); timer = undefined }
  const dirty = () => state.saving || options.snapshot() !== state.confirmed
  function begin(snapshot: string, revision: number) {
    generation++; cancelTimer(); controller?.abort(); controller = undefined
    Object.assign(state, { status: 'unchanged', confirmed: snapshot, revision, saving: false,
      paused: false, message: '', code: 0, completedAt: '', uncertainCreation: false })
  }
  function changed() {
    cancelTimer()
    if (disposed || !options.enabled() || state.saving || state.paused) return
    if (options.snapshot() === state.confirmed) {
      state.status = state.completedAt ? 'saved' : 'unchanged'; return
    }
    const reason = options.blocked()
    if (reason) { state.status = 'blocked'; state.message = reason; return }
    state.status = 'dirty'
    timer = setTimeout(() => { timer = undefined; void save('auto') }, options.delay ?? 3000)
    state.status = 'waiting'; state.message = ''
  }
  async function save(mode: SaveMode): Promise<boolean> {
    if (disposed || !options.enabled() || state.saving || state.status === 'conflict' || state.uncertainCreation) return false
    if (options.snapshot() === state.confirmed && options.identity()) return true
    if (mode === 'auto' && (state.paused || options.blocked())) return false
    cancelTimer()
    const key = generation, sent = options.snapshot(), revision = state.revision
    const isNew = !options.identity(), abort = new AbortController()
    controller = abort; state.saving = true; state.status = 'saving'; state.message = ''; state.code = 0
    let timeout: ReturnType<typeof setTimeout> | undefined
    try {
      const deadline = new Promise<never>((_, reject) => {
        timeout = setTimeout(() => { abort.abort(); reject(new Error('保存请求超时，结果尚未确认，请核对或手动重试。')) }, options.timeout ?? 15000)
      })
      const result = await Promise.race([options.persist(sent, revision, abort.signal), deadline])
      if (disposed || key !== generation) return false
      const accepted = options.accept(result, sent)
      state.confirmed = accepted.snapshot; state.revision = accepted.revision
      state.paused = false; state.status = 'saved'; state.completedAt = new Date().toLocaleTimeString('zh-CN')
      return true
    } catch (error: any) {
      if (disposed || key !== generation) return false
      state.code = Number(error?.status || 0); state.paused = true
      state.status = state.code === 409 ? 'conflict' : 'error'
      state.uncertainCreation = isNew && (!state.code || state.code >= 500)
      state.message = state.code === 409 ? '发生编辑冲突。已暂停自动保存，本页输入保留；请比较并重新读取服务器版本。'
        : state.code === 401 ? '登录已过期。本页输入保留，请在新标签页登录后手动重试。'
        : state.code === 403 ? '没有保存权限或安全令牌失效。本页输入保留，请核对权限后重试。'
        : state.code === 404 ? '记录不存在或已进入回收站。本页输入保留，请检查记录状态。'
        : state.code === 422 ? '字段验证未通过：' + String(error.message)
        : String(error?.message || error)
      if (state.uncertainCreation) state.message += '首次创建的结果不确定，已禁止重复创建；请先返回列表核对。'
      return false
    } finally {
      clearTimeout(timeout)
      if (!disposed && key === generation) {
        controller = undefined; state.saving = false
        if (!state.paused) changed()
      }
    }
  }
  function stop() { disposed = true; generation++; cancelTimer(); controller?.abort() }
  return { state, begin, changed, save, dirty, stop }
}
