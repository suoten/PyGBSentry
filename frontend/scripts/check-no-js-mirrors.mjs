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

const files = walk(root)

const vuePaths = new Set(files.filter((f) => f.endsWith('.vue')))
const vueJsMirrors = files.filter((f) => f.endsWith('.vue.js') && vuePaths.has(f.slice(0, -3)))
if (vueJsMirrors.length) {
  console.error('Found .vue.js mirrors (stale compiled copies next to .vue — delete them):')
  for (const f of vueJsMirrors.sort()) {
    console.error('-', path.relative(process.cwd(), f))
  }
  process.exit(1)
}

const js = new Set(files.filter(f => f.endsWith('.js')).map(f => f.slice(0, -3)))
const ts = new Set(
  files
    .filter(f => f.endsWith('.ts') || f.endsWith('.tsx'))
    .map(f => (f.endsWith('.tsx') ? f.slice(0, -4) : f.slice(0, -3)))
)

const conflicts = [...js].filter(base => ts.has(base)).sort()

if (conflicts.length) {
  console.error('Found JS mirrors shadowing TS:')
  for (const base of conflicts) {
    const rel = path.relative(process.cwd(), base)
    console.error(`- ${rel}.js (also has .ts/.tsx)`)
  }
  process.exit(1)
}

console.log('OK: no TS/JS mirror conflicts found in src/')

