const fs = require('fs');
const path = require('path');

const filePath = path.resolve(__dirname, '../src/views/AuditCenter.vue');
let content = fs.readFileSync(filePath, 'utf8');
const hasCRLF = content.includes('\r\n');
const eol = hasCRLF ? '\r\n' : '\n';

const oldImport = "import { getRoleInfo } from '../utils/auth'";
const newImport = "import { getVerifiedRoleInfo } from '../utils/auth'";

if (!content.includes(oldImport)) {
  console.error('OLD IMPORT NOT FOUND');
  process.exit(1);
}
if (content.includes(newImport)) {
  console.log('Already patched, skip.');
  process.exit(0);
}

content = content.replace(oldImport, newImport);
fs.writeFileSync(filePath, content, 'utf8');
console.log('AuditCenter.vue import fixed OK (eol=' + (hasCRLF ? 'CRLF' : 'LF') + ')');
