/**
 * 禁止在业务代码中直读 axios 错误体上的 response.data.detail（应使用 getFriendlyError / getApiErrorMessage）。
 * 允许名单：errorMessage 集中解析、登录页 OTP 等特判。
 *
 * 用法：
 *   - 在对应 frontend 包根下执行（cwd 须含 `src/`）：
 *     node ../../../tools/frontend/check-no-raw-axios-detail.mjs
 *   - 或显式传入包根目录（绝对/相对均可）：
 *     node tools/frontend/check-no-raw-axios-detail.mjs editions/open-source/frontend
 */
import fs from 'node:fs'
import path from 'node:path'

const pkgRoot = process.argv[2] ? path.resolve(process.cwd(), process.argv[2]) : process.cwd()
const root = path.resolve(pkgRoot, 'src')
if (!fs.existsSync(root)) {
  console.error(
    `未找到 ${path.relative(process.cwd(), root) || 'src'}：请在含 src/ 的 frontend 包根下执行，或传入包根路径作为第一个参数。当前 cwd=${process.cwd()}`
  )
  process.exit(1)
}

function walk(dir) {
  const out = []
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, ent.name)
    if (ent.isDirectory()) out.push(...walk(full))
    else if (ent.isFile()) out.push(full)
  }
  return out
}

/** 路径片段匹配（Windows / POSIX） */
function isAllowedFile(relPosix) {
  if (relPosix.endsWith('/utils/errorMessage.ts')) return true
  if (relPosix.endsWith('/views/Login.vue')) return true
  if (relPosix.endsWith('/views/AdminLogin.vue')) return true
  // 播放器/底层封装组件内部可能自处理 message，不强行收口
  if (relPosix.endsWith('/components/player/JessibucaPlayer.vue')) return true
  if (relPosix.endsWith('/components/player/RtcPlayer.vue')) return true
  return false
}

/** 与 errorMessage / 登录特判无关的直读 detail */
const FORBIDDEN_DETAIL =
  /\bresponse\?\.data\?\.detail\b|\bresponse\.data\?\.detail\b|\bresponse\?\.data\.detail\b/

/**
 * UI 场景中直接拼接 e.message / error.message（应统一经 getFriendlyError / getApiErrorMessage）
 * 目前只拦截两类：
 *  - ElMessage.error / ElMessage.warning(...) 中出现 *.message
 *  - 明确错误展示 ref（如 configError.value / error.value）直接赋值 *.message
 */
const FORBIDDEN_MESSAGE_IN_UI =
  /\bElMessage\.(?:error|warning)\([^)]*\b(?:e|err|error)\??\.message\b[^)]*\)/ ||
  /\b(?:configError|error|errMsg|errorMessage)\.value\s*=\s*[^;]*\b(?:e|err|error)\??\.message\b/

const files = walk(root).filter((f) => {
  const lower = f.toLowerCase()
  return lower.endsWith('.vue') || lower.endsWith('.ts') || lower.endsWith('.tsx')
})

const hits = []
for (const abs of files) {
  const rel = path.relative(process.cwd(), abs).split(path.sep).join('/')
  if (isAllowedFile(rel)) continue
  const text = fs.readFileSync(abs, 'utf8')
  const lines = text.split(/\r?\n/)
  lines.forEach((line, i) => {
    const trimmed = line.trim()
    if (trimmed.startsWith('//') || trimmed.startsWith('*')) return
    if (FORBIDDEN_DETAIL.test(line) || FORBIDDEN_MESSAGE_IN_UI.test(line)) {
      hits.push({ rel, line: i + 1, text: line.trim().slice(0, 200) })
    }
  })
}

if (hits.length) {
  console.error(
    '禁止在下列位置直读 response.data.detail，或在 UI 中直接拼接 e.message / error.message，请改用 getFriendlyError / getApiErrorMessage：'
  )
  for (const h of hits) {
    console.error(`- ${h.rel}:${h.line}  ${h.text}`)
  }
  console.error(
    '\n允许例外：src/utils/errorMessage.ts、src/views/Login.vue、src/views/AdminLogin.vue、src/components/player/JessibucaPlayer.vue、src/components/player/RtcPlayer.vue'
  )
  process.exit(1)
}

console.log(
  'OK: 未发现直读 axios response.data.detail，且 UI 中未直接使用 e.message / error.message（allowlist 文件除外）'
)
