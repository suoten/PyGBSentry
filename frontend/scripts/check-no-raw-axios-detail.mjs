import fs from 'node:fs'
import path from 'node:path'

const root = path.resolve(process.cwd(), 'src')

function walk(dir) {
  const out = []
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, ent.name)
    if (ent.isDirectory()) out.push(...walk(full))
    else if (ent.isFile()) out.push(full)
  }
  return out
}

const files = walk(root).filter(
  (f) => f.endsWith('.vue') || f.endsWith('.ts') || f.endsWith('.tsx')
)

const violations = []

for (const file of files) {
  const rel = path.relative(process.cwd(), file)
  const content = fs.readFileSync(file, 'utf-8')
  const lines = content.split('\n')
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    if (
      /\.(response\s*\.\s*data\s*\.\s*detail)\b/.test(line) &&
      !/getFriendlyError|getApiErrorMessage|errorMessage/.test(line) &&
      !/__tests__/.test(file) &&
      !/\.test\./.test(file) &&
      !/\.spec\./.test(file)
    ) {
      violations.push(`${rel}:${i + 1}: ${line.trim()}`)
    }
  }
}

if (violations.length) {
  console.error(
    'Found raw axios error.response.data.detail usage (use getFriendlyError/getApiErrorMessage instead):'
  )
  for (const v of violations) {
    console.error(' -', v)
  }
  process.exit(1)
}

console.log('OK: no raw axios .response.data.detail usage found in src/')
