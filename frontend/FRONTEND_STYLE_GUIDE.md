# PyGBSentry 前端样式规范

**版本**：v1.0
**日期**：2026-04-11
**目标读者**：前端工程师
**文档目的**：建立统一的设计规范和代码标准，确保前端代码风格一致、可维护

> **重要**：本规范为前端团队内部执行标准，所有新增代码必须遵守。重构阶段请参见 `docs/UI_REDESIGN.md`。

---

## 一、设计系统（Design Tokens）

### 1.1 设计原则

1. **单一来源**：所有样式值必须来自 `src/style.css` 的 CSS 变量，禁止硬编码
2. **语义化命名**：变量名表达含义，不表达值（如 `--el-color-danger` 而非 `--red-500`）
3. **层级分明**：Element Plus 变量 → 项目级变量 → 组件级变量

### 1.2 颜色系统

#### 主色系

```css
:root {
  /* Element Plus 主色（蓝色） */
  --el-color-primary: #409eff;
  --el-color-primary-light-3: #79bbff;
  --el-color-primary-light-5: #a0cfff;
  --el-color-primary-light-7: #c6e2ff;
  --el-color-primary-light-8: #d9ecff;
  --el-color-primary-light-9: #ecf5ff;
  --el-color-primary-dark-2: #337ecc;
  
  /* 语义色 */
  --el-color-success: #10b981;   /* 成功 / 在线 / 正常 */
  --el-color-warning: #f59e0b;   /* 警告 / 处理中 */
  --el-color-danger: #ef4444;    /* 危险 / 离线 / 错误 */
  --el-color-info: #64748b;      /* 信息 / 未知状态 */
  
  /* 文字色 */
  --el-text-color-primary: #1f2d3d;    /* 主要文字 */
  --el-text-color-regular: #334155;    /* 常规文字 */
  --el-text-color-secondary: #64748b;  /* 次要文字 */
  --el-text-color-placeholder: #94a3b8;/* 占位文字 */
  
  /* 边框色 */
  --el-border-color: #d9e1ec;
  --el-border-color-light: #e6ebf2;
  --el-border-color-lighter: #eef2f7;
  --el-border-color-extra-light: #f5f7fb;
  --el-border-color-hover: #b8c6d9;
}
```

#### 使用规范

```vue
<!-- ✅ 正确：使用 CSS 变量 -->
<template>
  <div class="status-badge status-badge--success">在线</div>
</template>

<style scoped>
.status-badge {
  color: var(--el-color-success);
  border: 1px solid var(--el-border-color-light);
  background: var(--el-color-success-light-9);
}
</style>

<!-- ❌ 错误：硬编码颜色 -->
<template>
  <div style="color: #10b981; border-color: #a7f3d0">在线</div>
</template>
```

### 1.3 圆角系统

```css
:root {
  /* 统一圆角 token */
  --el-border-radius-xs: 2px;   /* 微圆角（标签、小徽章） */
  --el-border-radius-sm: 4px;   /* 小圆角（输入框、按钮） */
  --el-border-radius-base: 6px; /* 基准圆角（卡片、对话框） */
  --el-border-radius-md: 8px;   /* 中圆角（面板、大卡片） */
  --el-border-radius-lg: 10px;  /* 大圆角（对话框、大面板） */
  --el-border-radius-xl: 12px;  /* 超大圆角（特殊容器） */
}
```

#### 使用规范

| 场景 | 圆角值 | CSS 变量 |
|------|--------|---------|
| 输入框 / 按钮 | 6px | `--el-border-radius-base` |
| 卡片 / 面板 | 8px | `--el-border-radius-md` |
| 对话框 | 10px | `--el-border-radius-lg` |
| 标签 / 徽章 | 4px | `--el-border-radius-sm` |
| 头像 | 50% | `--el-border-radius-circle` |

### 1.4 阴影系统

```css
:root {
  /* 阴影层级 */
  --el-box-shadow-xs: 0 1px 4px rgba(15, 23, 42, 0.03);
  --el-box-shadow-sm: 0 2px 8px rgba(15, 23, 42, 0.05);
  --el-box-shadow-base: 0 4px 12px rgba(15, 23, 42, 0.08);
  --el-box-shadow-lg: 0 8px 24px rgba(15, 23, 42, 0.12);
  --el-box-shadow-xl: 0 12px 32px rgba(15, 23, 42, 0.16);
}
```

#### 使用规范

| 场景 | 阴影 | CSS 变量 |
|------|------|---------|
| 页面卡片（默认） | 轻微阴影 | `--el-box-shadow-sm` |
| 卡片悬停 | 中等阴影 | `--el-box-shadow-base` |
| 对话框 | 大阴影 | `--el-box-shadow-lg` |
| 弹出菜单 | 中等阴影 | `--el-box-shadow-base` |
| 禁用（无阴影） | 无阴影 | `none` |

### 1.5 间距系统

```css
:root {
  /* 间距 token（4px 基准网格） */
  --el-space-1: 4px;
  --el-space-2: 8px;
  --el-space-3: 12px;
  --el-space-4: 16px;
  --el-space-5: 20px;
  --el-space-6: 24px;
  --el-space-8: 32px;
  --el-space-10: 40px;
  --el-space-12: 48px;
  
  /* 内容区间距 */
  --el-content-padding-xs: 8px;
  --el-content-padding-sm: 12px;
  --el-content-padding-base: 16px;
  --el-content-padding-lg: 20px;
  --el-content-padding-xl: 24px;
}
```

#### 使用规范

- **优先使用 Tailwind**：如 `p-4`（16px）、`gap-2`（8px）等 Tailwind 类
- **组件内间距**：优先用 Tailwind，如不够用再自定义 CSS
- **禁止 magic number**：如 `padding: 13px`、`margin-top: 7px` 等不规则值

### 1.6 字体系统

```css
:root {
  /* 字号 */
  --el-font-size-xs: 12px;
  --el-font-size-sm: 13px;
  --el-font-size-base: 14px;
  --el-font-size-md: 15px;
  --el-font-size-lg: 16px;
  --el-font-size-xl: 18px;
  --el-font-size-2xl: 20px;
  --el-font-size-3xl: 24px;
  
  /* 字体栈 */
  --el-font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Hiragino Sans GB',
    'Microsoft YaHei', '微软雅黑', Arial, sans-serif;
  
  /* 行高 */
  --el-line-height-tight: 1.25;
  --el-line-height-normal: 1.5;
  --el-line-height-relaxed: 1.75;
}
```

---

## 二、组件规范

### 2.0 图标规范

#### 图标库选择

**必须使用** Element Plus Icons，禁止使用 emoji 或其他图标库：

| 场景 | 图标 | 组件 |
|------|------|------|
| 添加/新建 | `Plus` | `<el-icon><Plus /></el-icon>` |
| 编辑 | `Edit` 或 `EditPen` | `<el-icon><Edit /></el-icon>` |
| 删除 | `Delete` 或 `DeleteFilled` | `<el-icon><Delete /></el-icon>` |
| 查看/详情 | `View` 或 `InfoFilled` | `<el-icon><View /></el-icon>` |
| 搜索 | `Search` | `<el-icon><Search /></el-icon>` |
| 刷新 | `Refresh` 或 `RefreshRight` | `<el-icon><Refresh /></el-icon>` |
| 设置 | `Setting` | `<el-icon><Setting /></el-icon>` |
| 导出 | `Download` | `<el-icon><Download /></el-icon>` |
| 导入 | `Upload` | `<el-icon><Upload /></el-icon>` |
| 关闭 | `Close` | `<el-icon><Close /></el-icon>` |
| 成功 | `CircleCheckFilled` | `<el-icon><CircleCheckFilled /></el-icon>` |
| 失败/错误 | `CircleCloseFilled` | `<el-icon><CircleCloseFilled /></el-icon>` |
| 警告 | `WarningFilled` | `<el-icon><WarningFilled /></el-icon>` |
| 加载中 | `Loading`（配合 CSS `animate-spin`） | `<el-icon class="animate-spin"><Loading /></el-icon>` |

#### ❌ 禁止的图标用法

```vue
<!-- ❌ 错误：使用 emoji 作为图标 -->
<button>➕ 添加</button>
<span>✅ 成功</span>
<span>❌ 失败</span>

<!-- ❌ 错误：使用非 Element Plus 图标库 -->
<img src="icon.svg" />
<i class="iconfont icon-add" />
```

#### ✅ 正确用法

```vue
<!-- ✅ 正确：使用 Element Plus Icons -->
<el-button type="primary">
  <el-icon class="mr-1"><Plus /></el-icon>
  新增
</el-button>

<!-- ✅ 正确：按钮仅图标时添加 aria-label -->
<el-button circle @click="handleDelete" aria-label="删除">
  <el-icon><Delete /></el-icon>
</el-button>

<!-- ✅ 正确：按钮带文字时图标在左侧 -->
<el-button type="primary">
  <el-icon class="mr-1"><View /></el-icon>
  查看详情
</el-button>
```

### 2.1 Dialog（对话框）

#### 全局样式覆盖（style.css）

```css
/* 所有对话框统一样式 */
.el-dialog {
  border-radius: var(--el-border-radius-lg);
  box-shadow: var(--el-box-shadow-xl);
}

.el-dialog__header {
  padding: var(--el-dialog-header-padding, 14px 18px);
  background: linear-gradient(180deg, #fbfcfe 0%, #f7f9fc 100%);
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.el-dialog__body {
  padding: var(--el-content-padding-base);
}

.el-dialog__footer {
  padding: 12px 18px 14px;
  background: #fafbfd;
  border-top: 1px solid var(--el-border-color-lighter);
}
```

#### 推荐的 Dialog 结构

```vue
<template>
  <el-dialog
    v-model="dialogVisible"
    :title="dialogTitle"
    width="640px"
    class="app-dialog"
    :close-on-click-modal="false"
    destroy-on-close
  >
    <!-- 对话框内容 -->
    <el-form :model="form" label-width="100px">
      <!-- 表单项 -->
    </el-form>
    
    <!-- 自定义 footer（可选） -->
    <template #footer>
      <span class="dialog-footer">
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleConfirm">确定</el-button>
      </span>
    </template>
  </el-dialog>
</template>
```

#### ❌ 禁止的 Dialog 写法

```vue
<!-- ❌ 错误：隐藏默认 header 使用自定义样式 -->
<el-dialog v-model="visible" class="custom-dialog">
  <template #header>
    <div class="custom-dialog-header">  <!-- 不要这样做 -->
      <span>标题</span>
    </div>
  </template>
</template>

<!-- ❌ 错误：自定义 body/footer 背景色 -->
<style scoped>
.el-dialog__body {
  background: #f8fafc;  /* 不要硬编码 */
}
</style>
```

### 2.2 Table（表格）

#### 全局样式覆盖（style.css）

```css
.el-table {
  --el-table-border-color: var(--el-border-color-lighter);
  --el-table-header-bg-color: #f8fafc;
  --el-table-header-text-color: #475569;
  --el-table-row-hover-bg-color: #f5f9ff;
  border-radius: var(--el-border-radius-md);
  overflow: hidden;
}

.el-table .el-table__header th {
  font-size: 13px;
  font-weight: 600;
  color: #475569;
}

.el-table .el-table__cell {
  padding: 11px 12px;
  font-size: 13px;
}
```

#### 分页器规范

```vue
<template>
  <div class="pagination-wrapper">
    <el-pagination
      v-model:current-page="currentPage"
      v-model:page-size="pageSize"
      :page-sizes="[10, 20, 50, 100]"
      :total="total"
      layout="total, sizes, prev, pager, next, jumper"
      background
    />
  </div>
</template>

<style scoped>
.pagination-wrapper {
  /* ✅ 正确：使用全局样式 */
  display: flex;
  justify-content: flex-end;
  align-items: center;
  padding: 10px 14px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-top: none;
  border-radius: 0 0 var(--el-border-radius-md) var(--el-border-radius-md);
}
</style>
```

### 2.3 Form（表单）

#### 表单规范

```vue
<template>
  <el-form
    ref="formRef"
    :model="formData"
    :rules="formRules"
    label-width="100px"
    class="app-form"
  >
    <el-form-item label="用户名" prop="username">
      <el-input v-model="formData.username" placeholder="请输入用户名" />
    </el-form-item>
    
    <el-form-item label="状态" prop="status">
      <el-select v-model="formData.status" placeholder="请选择">
        <el-option label="启用" value="1" />
        <el-option label="禁用" value="0" />
      </el-select>
    </el-form-item>
  </el-form>
</template>

<style scoped>
.app-form {
  /* ✅ 正确：表单样式继承全局 token */
}

.app-form .el-input,
.app-form .el-select {
  width: 100%;
  max-width: 360px;
}
</style>
```

#### label-width 规范

| 表单类型 | label-width | 示例 |
|---------|------------|------|
| 标准表单 | `100px` | 用户管理、设备配置 |
| 紧凑表单 | `80px` | 标签编辑、快捷配置 |
| 宽表单 | `120px` | 录像配置、通道配置 |

### 2.4 Button（按钮）

#### 按钮使用规范

```vue
<template>
  <!-- 主要操作 -->
  <el-button type="primary">确定</el-button>

  <!-- 次要操作 -->
  <el-button>取消</el-button>

  <!-- 危险操作 -->
  <el-button type="danger">删除</el-button>

  <!-- 文字按钮（辅助操作） -->
  <el-button type="primary" text>查看详情</el-button>

  <!-- 带图标 -->
  <el-button type="primary">
    <el-icon><Plus /></el-icon>
    新增
  </el-button>
</template>
```

#### 按钮尺寸规范

| 场景 | 推荐尺寸 | 说明 |
|------|---------|------|
| 表格工具栏 | `size="small"` | 紧凑布局 |
| 表单操作区 | `size="default"` | 标准按钮 |
| 主要操作区 | `size="default"` | 最常用 |
| 弹窗底部按钮 | `size="default"` | 保持一致 |
| 页面级主操作 | `size="large"` | 突出主操作 |

#### 按钮顺序规范

- **弹窗 footer**：取消按钮在左，确认按钮在右（主操作）
- **工具栏**：最常用操作在左侧，辅助操作在右侧

### 2.5 StatusBadge（状态徽章）

**必须使用** `StatusBadge` 组件，禁止手写 el-tag：

```vue
<template>
  <!-- ✅ 正确：使用 StatusBadge -->
  <StatusBadge :status="device.status" show-icon />

  <!-- ✅ 正确：自定义文本 -->
  <StatusBadge status="online" text="在线设备" />

  <!-- ❌ 错误：手写 el-tag -->
  <el-tag type="success" effect="dark" round>在线</el-tag>
</template>
```

**支持的自动状态**：`online` / `offline` / `success` / `error` / `warning` / `info` / `active` / `inactive` / `running` / `stopped` / `pending` 等。

### 2.6 ConfirmDialog（确认对话框）

**必须使用** `ConfirmDialog` 组件处理危险操作确认：

```vue
<script setup lang="ts">
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'

const showDeleteConfirm = ref(false)
const deleting = ref(false)

const handleDelete = async () => {
  deleting.value = true
  try {
    await deleteDevice(props.deviceId)
    ElMessage.success('删除成功')
    showDeleteConfirm.value = false
    emit('deleted')
  } catch {
    // error handled by interceptor
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <!-- ✅ 正确：使用 ConfirmDialog -->
  <ConfirmDialog
    v-model="showDeleteConfirm"
    v-model:loading="deleting"
    intent="danger"
    content="确定要删除该设备吗？删除后将无法恢复。"
    confirm-text="删除"
    @confirm="handleDelete"
  />
</template>
```

### 2.7 Card（卡片）

#### ❌ 禁止的按钮写法

```vue
<!-- ❌ 错误：自定义按钮颜色 -->
<el-button style="background: #10b981; color: white">启用</el-button>

<!-- ❌ 错误：自定义按钮尺寸 -->
<el-button style="height: 36px; padding: 0 20px">提交</el-button>

<!-- ❌ 错误：使用非 Element Plus 图标组件 -->
<button class="custom-btn">提交</button>
```

### 2.8 Card（卡片）

#### 卡片使用规范

```vue
<template>
  <!-- 使用全局 .app-card 样式 -->
  <div class="app-card">
    <div class="app-card__header">
      <span class="app-card__title">卡片标题</span>
      <el-button size="small">操作</el-button>
    </div>
    <div class="app-card__body">
      <!-- 卡片内容 -->
    </div>
  </div>
</template>

<style scoped>
/* ✅ 正确：使用 CSS 变量 */
.app-card {
  border-radius: var(--el-border-radius-md);
  box-shadow: var(--el-box-shadow-sm);
  border: 1px solid var(--el-border-color-lighter);
}

.app-card:hover {
  border-color: var(--el-border-color-hover);
  box-shadow: var(--el-box-shadow-base);
}
</style>
```

---

## 三、代码规范

### 3.1 CSS 书写规范

#### 优先级

1. **Tailwind CSS**（优先使用）
2. **全局 CSS 变量**（Tailwind 不满足时）
3. **组件 scoped 样式**（特殊情况）

#### ❌ 禁止的做法

```vue
<style scoped>
/* ❌ 错误：硬编码颜色 */
.box { background: #f5f7fb; }

/* ❌ 错误：硬编码文字颜色 */
.text { color: #1f2d3d; }

/* ❌ 错误：硬编码圆角 */
.card { border-radius: 8px; }

/* ❌ 错误：硬编码阴影 */
.panel { box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05); }

/* ❌ 错误：内联样式 */
<div style="color: #ef4444">错误</div>

/* ❌ 错误：不使用 Tailwind 工具类，用 padding-left: 8px */
.form-input :deep(.el-input__wrapper) { padding-left: 40px; }
```

#### ✅ 正确做法

```vue
<style scoped>
/* ✅ 正确：使用 CSS 变量 */
.box { background: var(--el-fill-color-lightest); }
.text { color: var(--el-text-color-primary); }
.card { border-radius: var(--el-border-radius-md); }
.panel { box-shadow: var(--el-box-shadow-sm); }

/* ✅ 正确：Tailwind + CSS 变量组合 */
.form-input :deep(.el-input__wrapper) {
  padding-left: 40px;  /* Tailwind 不支持的值，允许硬编码 */
  border-radius: var(--el-border-radius-base);
}
</style>
```

### 3.2 组件文件结构

```vue
<template>
  <!-- 模板部分 -->
</template>

<script setup lang="ts">
// 1. 导入
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'

// 2. Props / Emits
interface Props {
  userId: number
}
const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'refresh'): void
}>()

// 3. Store / Composables
const userStore = useUserStore()

// 4. 响应式数据
const loading = ref(false)
const formData = ref({ ... })

// 5. 计算属性
const isAdmin = computed(() => userStore.role === 'admin')

// 6. 方法
async function handleSubmit() { ... }
</script>

<style scoped>
/* 样式部分 */
/* 优先使用 Tailwind 类，尽量避免自定义 CSS */
/* 必须使用 CSS 变量，禁止硬编码 */
</style>
```

### 3.3 样式文件组织

```
src/
├── style.css              # 全局样式、Element Plus 覆盖、设计 token
├── styles/
│   ├── tokens.css         # ❌ 已废弃，请勿使用（合并到 style.css）
│   └── views/             # ❌ 已废弃，请勿使用（内联到组件 scoped）
├── views/                 # 页面视图
│   ├── UserManager.vue    # ✅ 样式内联在 <style scoped> 中
│   └── DeviceList.vue
└── components/            # 公共组件
    ├── common/
    │   ├── DialogTemplate.vue   # ✅ Dialog 模板组件
    │   └── LoadingState.vue     # ✅ 加载状态组件
    └── channel/
        └── ChannelEditDialog.vue
```

---

## 四、过渡动画规范

### 4.1 全局过渡动画

```css
/* style.css 中定义 */
:root {
  --transition-time-fast: 0.15s;
  --transition-time-base: 0.2s;
  --transition-time-slow: 0.3s;
}

/* 通用过渡 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity var(--transition-time-base);
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* 页面过渡（App.vue 已配置） */
.page-enter-active,
.page-leave-active {
  transition: opacity var(--transition-time-base), transform var(--transition-time-base);
}
.page-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
.page-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
```

### 4.2 组件过渡

```vue
<template>
  <Transition name="fade-slide">
    <div v-if="show" class="panel">
      内容
    </div>
  </Transition>
</template>

<style scoped>
.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.2s ease;
}
.fade-slide-enter-from,
.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
```

---

## 五、响应式规范

### 5.1 断点定义

| 断点 | 屏幕宽度 | Tailwind 前缀 |
|------|---------|-------------|
| 移动端 | < 768px | `sm:` |
| 平板 | 768px - 1024px | `md:` |
| 桌面 | 1024px - 1280px | `lg:` |
| 大屏 | > 1280px | `xl:` / `2xl:` |

### 5.2 组件响应式规则

- **Dialog 宽度**：移动端 `90vw`，平板 `560px`，桌面 `640px+`
- **Table 列隐藏**：移动端隐藏次要列，只保留核心列
- **表单布局**：移动端强制单列，桌面可双列
- **侧边栏**：移动端默认折叠，桌面默认展开

---

## 六、空状态与加载状态

### 6.1 空状态

**必须使用** `EmptyStateWithAction` 组件，禁止手写空状态：

```vue
<template>
  <!-- ✅ 正确：使用组件 -->
  <EmptyStateWithAction
    description="暂无数据"
  >
    <template #action>
      <el-button type="primary" @click="handleAdd">新增</el-button>
    </template>
  </EmptyStateWithAction>

  <!-- ❌ 错误：手写空状态 -->
  <div v-if="list.length === 0" class="empty-state">
    <el-empty description="暂无数据" />
    <el-button>新增</el-button>
  </div>
</template>
```

### 6.2 加载状态

**必须使用** `el-loading` 或骨架屏：

```vue
<template>
  <!-- ✅ 正确：使用 v-loading -->
  <div v-loading="loading">
    <!-- 内容 -->
  </div>

  <!-- ✅ 正确：使用 TableSkeleton -->
  <TableSkeleton v-if="loading" :rows="6" />
  <el-table v-else :data="tableData">
    <!-- 列定义 -->
  </el-table>
</template>
```

---

## 七、Accessibility（无障碍访问）

### 7.1 必填项

| 检查项 | 要求 |
|--------|------|
| 图片 alt | 所有 `<img>` 必须有 alt 属性 |
| 表单 label | 所有表单输入必须有关联 label |
| 键盘导航 | 所有交互可通过 Tab / Enter / Escape 完成 |
| 颜色对比度 | 文字与背景对比度 ≥ 4.5:1 |
| Skip Link | App.vue 已配置（跳转到 #main-content） |

### 7.2 ARIA 使用规范

```vue
<!-- ✅ 正确：按钮 aria-label -->
<el-button aria-label="截图">
  <el-icon><Camera /></el-icon>
</el-button>

<!-- ✅ 正确：搜索框 aria-label -->
<el-input
  v-model="keyword"
  placeholder="搜索设备"
  aria-label="搜索设备"
/>

<!-- ✅ 正确：对话框 aria-labelledby -->
<el-dialog
  v-model="visible"
  title="设备详情"
  aria-labelledby="dialog-title"
>
  <span id="dialog-title">设备详情</span>
</el-dialog>
```

---

## 八、检查清单

新增代码时自检：

- [ ] 颜色值是否使用了 CSS 变量（`var(--el-*)`）？
- [ ] 圆角值是否使用了 CSS 变量（`--el-border-radius-*`）？
- [ ] 阴影值是否使用了 CSS 变量（`--el-box-shadow-*`）？
- [ ] 间距是否优先使用 Tailwind（`p-4`、`gap-2` 等）？
- [ ] 是否有内联 style（`style=""`）需要迁移？
- [ ] 是否有硬编码颜色值（`#xxx`）需要迁移？
- [ ] 空状态是否使用了 `EmptyStateWithAction` 组件？
- [ ] 交互元素是否有适当的 `aria-label`？
- [ ] 组件是否放在了正确的目录（components/common/ vs components/channel/）？

---

## 九、迁移指南（从旧规范到新规范）

### 9.1 旧 token 系统 → 新 token 系统

| 旧写法 | 新写法 |
|--------|--------|
| `border-radius: var(--ds-radius-md)` | `border-radius: var(--el-border-radius-base)` |
| `box-shadow: var(--ds-shadow-1)` | `box-shadow: var(--el-box-shadow-xs)` |
| `padding: var(--ds-space-3)` | `padding: 12px` 或 Tailwind `p-3` |

### 9.2 硬编码颜色 → CSS 变量

| 旧写法 | 新写法 |
|--------|--------|
| `color: #4d8dff` | `color: var(--el-color-primary)` |
| `color: #ef4444` | `color: var(--el-color-danger)` |
| `color: #10b981` | `color: var(--el-color-success)` |
| `background: #f8fafc` | `background: var(--el-fill-color-light)` |
| `background: #f5f7fb` | `background: var(--el-app-content-bg, #f5f7fb)` |

### 9.3 旧 CSS 文件 → 内联 scoped

| 旧写法 | 新写法 |
|--------|--------|
| `src/styles/views/UserManager.css`（外部文件） | 迁移到 `UserManager.vue` 的 `<style scoped>` |

---

**文档版本**：v1.1
**创建日期**：2026-04-11
**最后更新**：2026-04-11
**本次更新**：新增 2.0 图标规范、2.5 StatusBadge、2.6 ConfirmDialog 章节；补充按钮尺寸/顺序规范
**维护人**：前端团队
**相关文档**：`docs/UI_REDESIGN.md`
