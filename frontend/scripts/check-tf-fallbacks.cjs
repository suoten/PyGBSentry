/* eslint-disable */
// 临时脚本：精确检查 tf('key', '中文兜底') 中 key 是否在 zh-CN.ts 中存在（按点路径）
const fs = require('fs')
const path = require('path')

const srcRoot = path.resolve(__dirname, '..', 'src')

function walk(dir, out = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) walk(p, out)
    else if (/\.(vue|ts|tsx)$/.test(e.name)) out.push(p)
  }
  return out
}

const files = walk(srcRoot)
const re = /tf\(\s*['"]([^'"]+)['"]\s*,\s*['"]([^'"]*[\u4e00-\u9fa5][^'"]*)['"]/g

const pairs = []
for (const f of files) {
  const txt = fs.readFileSync(f, 'utf8')
  let m
  while ((m = re.exec(txt)) !== null) {
    pairs.push({ key: m[1], fallback: m[2], file: path.relative(srcRoot, f) })
  }
}

console.log('Total tf calls with Chinese fallback:', pairs.length)

// 加载 zh-CN.ts 并 require 它来得到对象
// 由于是 TS，用简单 require 可能失败，所以用动态 eval 方式
const zhPath = path.join(srcRoot, 'locales', 'zh-CN.ts')
const zhTxt = fs.readFileSync(zhPath, 'utf8')
// 去掉 "export default "，再用 eval
const objBody = zhTxt.replace(/^export\s+default\s+/m, '').replace(/;\s*$/, '')
let zhObj
try {
  zhObj = eval('(' + objBody + ')')
} catch (e) {
  console.error('Failed to parse zh-CN.ts:', e.message)
  process.exit(1)
}

function hasKey(obj, dotted) {
  const parts = dotted.split('.')
  let cur = obj
  for (const p of parts) {
    if (cur == null || typeof cur !== 'object') return false
    if (!(p in cur)) return false
    cur = cur[p]
  }
  return typeof cur === 'string'
}

const missing = []
const present = []
for (const p of pairs) {
  if (hasKey(zhObj, p.key)) present.push(p)
  else missing.push(p)
}

console.log('Present (exact path):', present.length)
console.log('Missing (exact path):', missing.length)

console.log('\n=== Missing unique keys ===')
const missingUnique = new Map()
for (const p of missing) {
  if (!missingUnique.has(p.key)) missingUnique.set(p.key, p)
}
console.log('Unique missing:', missingUnique.size)
for (const [k, p] of missingUnique) {
  console.log(`  ${k}  =>  ${p.fallback}  (in ${p.file})`)
}

const allUnique = new Map()
for (const p of pairs) {
  if (!allUnique.has(p.key)) allUnique.set(p.key, p)
}
console.log('\nUnique total:', allUnique.size)
