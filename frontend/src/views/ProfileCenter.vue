<template>
  <div class="app-page space-y-4">
    <PageContainer>
      <template #header>
        <PageHeader title="个人资料" description="维护基础信息，并可在此修改登录密码" />
      </template>

      <div class="profile-grid">
        <TableCard>
          <template #header>
            <div class="font-medium">基础信息</div>
          </template>

          <el-form ref="profileFormRef" :model="profileForm" label-width="90px">
            <el-form-item>
              <template #label>
                <span class="readonly-label"><el-icon><Lock /></el-icon>用户名</span>
              </template>
              <el-input :model-value="me?.username || '-'" readonly class="readonly-input">
                <template #append>只读</template>
              </el-input>
            </el-form-item>
            <el-form-item>
              <template #label>
                <span class="readonly-label"><el-icon><Lock /></el-icon>租户</span>
              </template>
              <el-input :model-value="me?.tenant_id || '-'" readonly class="readonly-input">
                <template #append>只读</template>
              </el-input>
            </el-form-item>
            <el-form-item>
              <template #label>
                <span class="readonly-label"><el-icon><Lock /></el-icon>角色</span>
              </template>
              <el-input :model-value="me?.role || '-'" readonly class="readonly-input">
                <template #append>只读</template>
              </el-input>
            </el-form-item>
            <el-form-item label="姓名">
              <el-input v-model="profileForm.full_name" maxlength="64" placeholder="请输入姓名" clearable />
            </el-form-item>
            <el-form-item label="邮箱">
              <el-input v-model="profileForm.email" maxlength="128" placeholder="请输入邮箱" clearable />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="savingProfile" @click="saveProfile">保存资料</el-button>
              <el-button :disabled="savingProfile" @click="resetProfileForm">重置</el-button>
            </el-form-item>
          </el-form>
        </TableCard>

        <TableCard>
          <template #header>
            <div class="font-medium">修改密码</div>
          </template>

          <el-form ref="passwordFormRef" :model="passwordForm" :rules="passwordRules" label-width="90px">
            <el-form-item label="当前密码" prop="current_password">
              <el-input
                v-model="passwordForm.current_password"
                type="password"
                show-password
                autocomplete="current-password"
                placeholder="请输入当前密码"
              />
            </el-form-item>
            <el-form-item label="新密码" prop="new_password">
              <el-input
                v-model="passwordForm.new_password"
                type="password"
                show-password
                autocomplete="new-password"
                placeholder="请输入新密码（至少 8 位）"
              />
            </el-form-item>
            <el-form-item label="确认密码" prop="confirm_password">
              <el-input
                v-model="passwordForm.confirm_password"
                type="password"
                show-password
                autocomplete="new-password"
                placeholder="请再次输入新密码"
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="changingPassword" @click="changePassword">{{ t('profile.changePassword') }}</el-button>  <!-- FIXED: P3 i18n -->
              <el-button :disabled="changingPassword" @click="resetPasswordForm">{{ t('common.clear') }}</el-button>  <!-- FIXED: P3 i18n -->
            </el-form-item>
          </el-form>
        </TableCard>
      </div>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import http from '../utils/http'

import { ElMessage } from 'element-plus'
import { Lock } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import { getFriendlyError } from '../utils/errorMessage'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import { useI18n } from 'vue-i18n'  // FIXED: P3 i18n

const { t } = useI18n()  // FIXED: P3 i18n

type UserMe = {
  username: string
  full_name?: string | null
  email?: string | null
  tenant_id?: string | null
  role?: string | null
}

const me = ref<UserMe | null>(null)
const savingProfile = ref(false)
const changingPassword = ref(false)
const profileFormRef = ref<FormInstance>()
const passwordFormRef = ref<FormInstance>()

const profileForm = reactive({
  full_name: '',
  email: ''
})

const passwordForm = reactive({
  current_password: '',
  new_password: '',
  confirm_password: ''
})

const passwordRules: FormRules<typeof passwordForm> = {
  current_password: [{ required: true, message: '请输入当前密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        const text = String(value || '')
        if (text.length < 8) return callback(new Error('新密码至少 8 位'))
        if (text === String(passwordForm.current_password || '')) return callback(new Error('新密码不能与当前密码一致'))
        callback()
      },
      trigger: 'blur'
    }
  ],
  confirm_password: [
    { required: true, message: '请确认新密码', trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (String(value || '') !== String(passwordForm.new_password || '')) return callback(new Error('两次输入的新密码不一致'))
        callback()
      },
      trigger: 'blur'
    }
  ]
}

// FIXED: 添加try-catch防止API异常导致页面白屏
const loadMe = async () => {
  try {
    const res = await http.get('/api/v1/users/me')
    me.value = res.data
    profileForm.full_name = String(res.data?.full_name || '')
    profileForm.email = String(res.data?.email || '')
  } catch {
    ElMessage.error('加载个人资料失败')
  }
}

const resetProfileForm = () => {
  profileForm.full_name = String(me.value?.full_name || '')
  profileForm.email = String(me.value?.email || '')
}

const resetPasswordForm = () => {
  passwordForm.current_password = ''
  passwordForm.new_password = ''
  passwordForm.confirm_password = ''
  passwordFormRef.value?.clearValidate()
}

const saveProfile = async () => {
  savingProfile.value = true
  try {
    await http.put('/api/v1/users/me', {
      full_name: profileForm.full_name.trim() || null,
      email: profileForm.email.trim() || null
    })
    await loadMe()
    ElMessage.success('个人资料已保存')
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    savingProfile.value = false
  }
}

const changePassword = async () => {
  const ok = await passwordFormRef.value?.validate().catch(() => false)
  if (!ok) return
  changingPassword.value = true
  try {
    await http.post('/api/v1/users/me/change-password', {
      current_password: passwordForm.current_password,
      new_password: passwordForm.new_password
    })
    resetPasswordForm()
    ElMessage.success('密码修改成功，请使用新密码重新登录')
  } catch (e: unknown) {
    const friendly = getFriendlyError(e)
    ElMessage.error(friendly.suggestion ? `${friendly.message}（${friendly.suggestion}）` : friendly.message)
  } finally {
    changingPassword.value = false
  }
}

onMounted(() => {
  loadMe().catch(() => {
    ElMessage.error('加载个人资料失败')
  })
})
</script>

<style scoped>
.profile-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.readonly-input :deep(.el-input-group__append) {
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-light);
}

.readonly-input :deep(.el-input__wrapper) {
  background: var(--el-fill-color-lighter);
}

.readonly-input :deep(input) {
  color: var(--el-text-color-secondary);
  cursor: not-allowed;
}

.readonly-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--el-text-color-secondary);
}

.readonly-label :deep(.el-icon) {
  font-size: 13px;
}

@media (max-width: 1024px) {
  .profile-grid {
    grid-template-columns: 1fr;
  }
}
</style>
