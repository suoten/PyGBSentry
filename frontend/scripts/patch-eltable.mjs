/**
 * patch-eltable.mjs
 *
 * P0-FIX: 修补 Element Plus el-table 的 "$e is not iterable" 崩溃
 *
 * 根因：el-table 内部 setData → updateAllSelected 用 for...of 迭代 data，
 * 当 data 不是数组时直接崩溃。此脚本在 node_modules 中添加 Array.isArray 防御。
 *
 * 此脚本在 npm install 后自动运行（postinstall）。
 */
import { readFileSync, writeFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const storeFile = resolve(__dirname, '../node_modules/element-plus/es/components/table/src/store/index.mjs')

const MARKER = '// P0-FIX: patch-eltable Array.isArray guard'

try {
  let content = readFileSync(storeFile, 'utf-8')

  // 已经修补过，跳过
  if (content.includes(MARKER) || content.includes('P0-FIX')) {
    console.log('[patch-eltable] Already patched, skipping.')
    process.exit(0)
  }

  // 在 setData 函数开头添加 Array.isArray 防御
  const original = '\tsetData(states, data) {\n\t\tconst dataInstanceChanged = unref(states._data) !== data;'
  const patched = `\tsetData(states, data) {\n\t\t${MARKER}\n\t\tdata = Array.isArray(data) ? data : [];\n\t\tconst dataInstanceChanged = unref(states._data) !== data;`

  if (!content.includes(original)) {
    console.warn('[patch-eltable] Could not find target code to patch. Element Plus may have been updated. Skipping.')
    process.exit(0)
  }

  content = content.replace(original, patched)
  writeFileSync(storeFile, content, 'utf-8')
  console.log('[patch-eltable] Successfully patched el-table setData with Array.isArray guard.')
} catch (err) {
  console.warn('[patch-eltable] Patch failed (non-fatal):', err.message)
  process.exit(0) // 不阻断 npm install
}
