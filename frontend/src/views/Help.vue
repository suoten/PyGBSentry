<template>
  <div class="app-page space-y-4">
    <PageContainer>
      <template #header>
        <PageHeader :title="t('helpPage.title')" :description="t('helpPage.description')" />
      </template>

      <TableCard v-loading="loading">
        <el-tabs v-model="activeTab" type="border-card" class="border-0">
          <el-tab-pane v-for="tab in helpDocs" :key="tab.id" :label="tab.tab_name" :name="tab.id">
            <el-collapse v-if="tab.items && tab.items.length > 0" class="mt-2">
              <el-collapse-item v-for="(item, index) in tab.items" :key="index" :title="item.title" :name="String(index)">
                <div v-html="sanitizeHtml(item.content)" class="text-sm" style="color: var(--el-text-color-regular)"></div>
              </el-collapse-item>
            </el-collapse>
            <el-empty v-else :description="t('helpPage.noContent')" />
          </el-tab-pane>
        </el-tabs>
      </TableCard>
    </PageContainer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import api from '@/utils/http'
import DOMPurify from 'dompurify'
import PageContainer from '../components/PageContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import TableCard from '../components/TableCard.vue'
import { showError } from '../utils/feedback'

const { t } = useI18n()

interface HelpItem {
  title: string
  content: string
}

const sanitizeHtml = (html: string): string => {
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ['p', 'br', 'b', 'i', 'em', 'strong', 'a', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'pre', 'code', 'table', 'thead', 'tbody', 'tr', 'th', 'td'],
    ALLOWED_ATTR: ['href', 'target', 'class']
  })
}

interface HelpTab {
  id: string
  tab_name: string
  items: HelpItem[]
}

const loading = ref(false)
const helpDocs = ref<HelpTab[]>([])
const activeTab = ref('')

const fetchHelpDocs = async () => {
  loading.value = true
  try {
    const res = await api.get('/api/v1/ops/help-docs')
    if (Array.isArray(res.data)) {
      helpDocs.value = res.data
      if (helpDocs.value.length > 0) {
        activeTab.value = helpDocs.value[0].id
      }
    }
  } catch (e) {
    showError(t('helpPage.loadFailed'), e)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchHelpDocs()
})
</script>
