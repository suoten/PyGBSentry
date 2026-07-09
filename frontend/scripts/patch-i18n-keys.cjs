const fs = require('fs');
const path = require('path');

function patchFile(filePath, oldText, newText, label) {
  const full = path.resolve(__dirname, filePath);
  let content = fs.readFileSync(full, 'utf8');
  // Detect line ending
  const hasCRLF = content.includes('\r\n');
  const eol = hasCRLF ? '\r\n' : '\n';
  const oldNorm = oldText.replace(/\n/g, eol);
  const newNorm = newText.replace(/\n/g, eol);
  if (!content.includes(oldNorm)) {
    console.error('[' + label + '] OLD NOT FOUND (eol=' + (hasCRLF ? 'CRLF' : 'LF') + ')');
    process.exit(1);
  }
  if (content.includes(newNorm)) {
    console.log('[' + label + '] Already patched, skip.');
    return;
  }
  content = content.replace(oldNorm, newNorm);
  fs.writeFileSync(full, content, 'utf8');
  console.log('[' + label + '] Updated OK (eol=' + (hasCRLF ? 'CRLF' : 'LF') + ')');
}

patchFile(
  '../src/locales/zh-CN.ts',
  "    upgrade5xx: '升级5xx',\n    resumeAutoRefresh: '恢复自动刷新',",
  "    upgrade5xx: '升级5xx',\n    quickUpgrade: '快速升级',\n    advancedFilter: '高级筛选',\n    resumeAutoRefresh: '恢复自动刷新',",
  'zh-CN'
);

patchFile(
  '../src/locales/en-US.ts',
  "    upgrade5xx: 'Upgrade 5xx',\n    resumeAutoRefresh: 'Resume Auto Refresh',",
  "    upgrade5xx: 'Upgrade 5xx',\n    quickUpgrade: 'Quick Upgrade',\n    advancedFilter: 'Advanced Filter',\n    resumeAutoRefresh: 'Resume Auto Refresh',",
  'en-US'
);
