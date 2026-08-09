#!/usr/bin/env node
/**
 * 扫描前端代码中所有 API 调用路径（http.xxx 和 api.xxx），
 * 并与后端 openapi.json 端点列表对比，找出可能 404 的 API 调用。
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const srcDir = path.join(__dirname, 'src');

// 收集前端代码中所有 API 路径
const apiPaths = new Map(); // path -> Set<files>

function walkDir(dir) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === '__tests__' || entry.name === 'node_modules') continue;
      walkDir(fullPath);
    } else if (/\.(ts|vue|js)$/.test(entry.name)) {
      const content = fs.readFileSync(fullPath, 'utf-8');
      // 匹配 http.get/post/put/delete/patch 或 api.get/post/put/delete/patch
      // 后跟字符串字面量或模板字面量
      const regex = /(?:http|api)\.(get|post|put|delete|patch)\(\s*(['"`])([^'"`]+)\2/g;
      let match;
      while ((match = regex.exec(content)) !== null) {
        const apiPath = match[3];
        if (!apiPath.startsWith('/api/')) continue;
        // 处理动态路径（包含 ${...}）
        let normalizedPath;
        if (apiPath.includes('${')) {
          normalizedPath = apiPath.split('${')[0].replace(/\/$/, '');
        } else {
          normalizedPath = apiPath;
        }
        if (!apiPaths.has(normalizedPath)) {
          apiPaths.set(normalizedPath, new Set());
        }
        apiPaths.get(normalizedPath).add(fullPath);
      }
    }
  }
}

walkDir(srcDir);

// 读取后端端点列表（JSON 数组，去除 BOM）
const endpointsText = fs.readFileSync(path.join(__dirname, '_api_endpoints_list.txt'), 'utf-8').replace(/^\uFEFF/, '');
const endpoints = JSON.parse(endpointsText);

console.log(`前端 API 路径数: ${apiPaths.size}`);
console.log(`后端端点数: ${endpoints.length}`);
console.log('\n=== 检查前端 API 是否在后端存在 ===\n');

const missing = [];
const found = [];
for (const [apiPath, files] of apiPaths) {
  // 完全匹配
  const exactMatch = endpoints.includes(apiPath);
  // 前缀匹配（处理动态路径）
  const prefixMatch = endpoints.some(ep => {
    const epStatic = ep.split('{')[0].replace(/\/$/, '');
    if (epStatic === apiPath) return true;
    // 端点的静态部分以前端路径为前缀（如 /api/v1/devices/{id} 匹配 /api/v1/devices）
    if (epStatic.startsWith(apiPath + '/')) return true;
    // 前端路径以端点静态部分为前缀（如 /api/v1/alarms/link-rules 匹配 /api/v1/alarms/link-rules/{id}）
    if (apiPath.startsWith(epStatic + '/')) return true;
    return false;
  });

  if (exactMatch || prefixMatch) {
    found.push({ path: apiPath, files: [...files] });
  } else {
    missing.push({ path: apiPath, files: [...files] });
  }
}

console.log(`✓ 存在的 API: ${found.length}`);
console.log(`✗ 缺失的 API: ${missing.length}\n`);

if (missing.length > 0) {
  console.log('=== ⚠️ 缺失的 API 列表（可能 404）===');
  for (const m of missing) {
    console.log(`\n  ${m.path}`);
    const uniqueFiles = [...new Set(m.files)];
    for (const f of uniqueFiles.slice(0, 3)) {
      console.log(`    在: ${path.relative(srcDir, f)}`);
    }
  }
}

// 把结果写入文件
const reportLines = [];
reportLines.push(`# 前端 API 调用 vs 后端端点对照报告`);
reportLines.push(``);
reportLines.push(`- 前端 API 路径数: ${apiPaths.size}`);
reportLines.push(`- 后端端点数: ${endpoints.length}`);
reportLines.push(`- ✓ 存在: ${found.length}`);
reportLines.push(`- ✗ 缺失: ${missing.length}`);
reportLines.push(``);
if (missing.length > 0) {
  reportLines.push(`## ⚠️ 缺失的 API（可能 404）`);
  reportLines.push(``);
  for (const m of missing) {
    reportLines.push(`- \`${m.path}\``);
    const uniqueFiles = [...new Set(m.files)];
    for (const f of uniqueFiles.slice(0, 3)) {
      reportLines.push(`  - 在: ${path.relative(srcDir, f)}`);
    }
  }
} else {
  reportLines.push(`## ✅ 全部 API 都在后端存在`);
}
reportLines.push(``);
reportLines.push(`## 已存在的 API 列表`);
reportLines.push(``);
for (const f of found) {
  reportLines.push(`- ✓ \`${f.path}\``);
}

fs.writeFileSync(path.join(__dirname, '_api_check_report.md'), reportLines.join('\n'), 'utf-8');
console.log(`\n报告已写入: _api_check_report.md`);
