// paperdepot — host 入口 v3（薄壳 + 热 impl + 把 ctx 传给 impl）
//
// 这个文件是「壳」：只注册路由，按 mtime 动态加载 lib/impl.js。
// 之所以单独版本号：ESM 缓存按路径，改已经加载过的壳不会生效；
// 稳定安装时用 paperdepot/host（内容与本文件一致）。
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

export const name = 'paperdepot'
export const inject = ['webServer']

const here = path.dirname(fileURLToPath(import.meta.url))
let cached = { key: '', handler: null }

async function handlerFor(config, ctx) {
  const impl = path.join(here, 'impl.js')
  const st = fs.statSync(impl)
  const key = `${st.mtimeMs}:${st.size}`
  if (!cached.handler || cached.key !== key) {
    const mod = await import(pathToFileURL(impl).href + '?v=' + key)
    cached = { key, handler: mod.createHandler(config || {}, { ctx }) }
  }
  return cached.handler
}

export function apply(ctx, config) {
  try {
    if (typeof ctx.webServer?.register !== 'function') {
      console.warn('[paperdepot] webServer service unavailable; host half disabled')
      return
    }
    ctx.effect(() =>
      ctx.webServer.register({
        kind: 'prefix',
        path: '/paperdepot/api',
        handler: (req, res) => {
          handlerFor(config, ctx)
            .then((h) => h(req, res))
            .catch((err) => {
              try {
                res.writeHead(500, { 'Content-Type': 'application/json; charset=utf-8' })
                res.end(JSON.stringify({ ok: false, error: String((err && err.message) || err) }))
              } catch {
                /* ignore */
              }
            })
        },
      }),
    )
    console.log('[paperdepot] host ready (host3, hot impl)')
  } catch (err) {
    console.error('[paperdepot] host apply failed:', err)
  }
}
