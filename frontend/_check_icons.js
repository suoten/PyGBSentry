#!/usr/bin/env node
/**
 * 扫描所有 Vue 组件中使用的 Element Plus 图标组件，
 * 检查是否在 import 语句中正确导入。
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const srcDir = path.join(__dirname, 'src');

const issues = [];

function walkDir(dir) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === '__tests__' || entry.name === 'node_modules') continue;
      walkDir(fullPath);
    } else if (/\.vue$/.test(entry.name)) {
      checkFile(fullPath);
    }
  }
}

function checkFile(filePath) {
  const content = fs.readFileSync(filePath, 'utf-8');
  
  // 跳过 setup 脚本不存在的情况
  const hasScript = content.includes('<script');
  if (!hasScript) return;
  
  // 找到所有使用的图标组件（PascalCase 形式，如 <Refresh />）
  // 匹配 <el-icon><XxxYyy /></el-icon> 或 <XxxYyy /> 单独使用
  const iconUsageRegex = /<el-icon[^>]*>\s*<([A-Z][a-zA-Z0-9]+)\s*\/?\s*>/g;
  const usedIcons = new Set();
  let match;
  while ((match = iconUsageRegex.exec(content)) !== null) {
    usedIcons.add(match[1]);
  }
  
  // 也检查直接使用的图标（不带 el-icon 包装）
  const directIconRegex = /<([A-Z][a-zA-Z0-9]+)\s+class="[^"]*icon[^"]*"/g;
  while ((match = directIconRegex.exec(content)) !== null) {
    usedIcons.add(match[1]);
  }
  
  if (usedIcons.size === 0) return;
  
  // 检查 import 语句中导入的图标
  const importRegex = /import\s+\{([^}]+)\}\s+from\s+['"]@element-plus\/icons-vue['"]/g;
  const importedIcons = new Set();
  while ((match = importRegex.exec(content)) !== null) {
    const icons = match[1].split(',').map(s => s.trim()).filter(Boolean);
    for (const icon of icons) {
      importedIcons.add(icon);
    }
  }
  
  // 也检查 Components 注册（如果有的话）
  const componentsRegex = /components:\s*\{([^}]+)\}/g;
  while ((match = componentsRegex.exec(content)) !== null) {
    const components = match[1].split(',').map(s => s.trim()).filter(Boolean);
    for (const comp of components) {
      importedIcons.add(comp);
    }
  }
  
  // 找出未导入的图标
  const missing = [...usedIcons].filter(icon => !importedIcons.has(icon));
  
  if (missing.length > 0) {
    issues.push({
      file: path.relative(srcDir, filePath),
      missing,
      used: [...usedIcons],
      imported: [...importedIcons],
    });
  }
}

walkDir(srcDir);

console.log(`\n=== 图标导入检查报告 ===\n`);
console.log(`扫描的 .vue 文件中发现的图标使用问题: ${issues.length} 个\n`);

if (issues.length > 0) {
  for (const issue of issues) {
    console.log(`📄 ${issue.file}`);
    console.log(`  缺失的图标: ${issue.missing.join(', ')}`);
    console.log(`  已导入的图标: ${issue.imported.join(', ') || '(无)'}`);
    console.log('');
  }
} else {
  console.log('✅ 所有图标都已正确导入');
}

// 写入报告
const reportLines = ['# 图标导入检查报告', '', `发现 ${issues.length} 个问题`, ''];
for (const issue of issues) {
  reportLines.push(`## ${issue.file}`);
  reportLines.push(`- 缺失的图标: ${issue.missing.join(', ')}`);
  reportLines.push('');
}
fs.writeFileSync(path.join(__dirname, '_icon_check_report.md'), reportLines.join('\n'), 'utf-8');
