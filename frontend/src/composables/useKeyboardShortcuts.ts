import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import i18n from '@/locales' // FIXED: 国际化

const t = i18n.global.t // FIXED: 国际化

export interface ShortcutItem {
  key: string
  description: string
  action: () => void
  showInHelp?: boolean
  group?: string
}

let globalShortcuts: ShortcutItem[] = []

const keySequence = ref('')
let sequenceTimer: ReturnType<typeof setTimeout> | null = null

const SEQUENCE_TIMEOUT = 1000

const showHelp = ref(false)

let helpAction: (() => void) | null = null

export const registerHelpAction = (action: () => void) => {
  helpAction = action
}

export const getVisibleShortcuts = (): ShortcutItem[] => {
  return globalShortcuts.filter(s => s.showInHelp !== false)
}

export const getShortcutsByGroup = (): Record<string, ShortcutItem[]> => {
  const groups: Record<string, ShortcutItem[]> = {}
  for (const shortcut of getVisibleShortcuts()) {
    const group = shortcut.group || t('shortcut.groupOther') // FIXED: 国际化
    if (!groups[group]) groups[group] = []
    groups[group].push(shortcut)
  }
  return groups
}

const handleKeydown = (e: KeyboardEvent) => {
  const target = e.target as HTMLElement
  const isInput = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable
  if (isInput && e.key !== 'Escape') return

  if ((e.ctrlKey || e.metaKey) && e.key !== 'k') return

  if (e.key === 'Escape') {
    if (showHelp.value) {
      showHelp.value = false
      return
    }
    window.dispatchEvent(new CustomEvent('shortcut-escape'))
    return
  }

  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault()
    const shortcut = globalShortcuts.find(s => s.key === 'Ctrl+K')
    if (shortcut) shortcut.action()
    return
  }

  const key = e.key.toLowerCase()

  if (sequenceTimer) {
    clearTimeout(sequenceTimer)
  }

  if (key === 'g') {
    keySequence.value = 'g'
    sequenceTimer = setTimeout(() => {
      keySequence.value = ''
    }, SEQUENCE_TIMEOUT)
    return
  }

  if (keySequence.value === 'g') {
    const fullKey = 'g ' + key
    const shortcut = globalShortcuts.find(s => s.key === fullKey || s.key === `g ${key}`)
    if (shortcut) {
      e.preventDefault()
      shortcut.action()
      keySequence.value = ''
      if (sequenceTimer) {
        clearTimeout(sequenceTimer)
        sequenceTimer = null
      }
      return
    }
    keySequence.value = ''
    return
  }

  const singleKey = e.ctrlKey || e.metaKey ? null : key
  if (singleKey && !e.ctrlKey && !e.metaKey) {
    const ignoredKeys = ['tab', 'shift', 'alt', 'meta', 'capslock', 'enter', 'backspace', 'delete', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright', 'home', 'end', 'pageup', 'pagedown', 'insert', 'f1', 'f2', 'f3', 'f4', 'f5', 'f6', 'f7', 'f8', 'f9', 'f10', 'f11', 'f12']
    if (!ignoredKeys.includes(singleKey)) {
      const shortcut = globalShortcuts.find(s => s.key === singleKey)
      if (shortcut && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault()
        shortcut.action()
      }
    }
  }
}

export const useKeyboardShortcuts = () => {
  const router = useRouter()

  if (globalShortcuts.length === 0) {
    globalShortcuts = [
      { key: 'g d', description: t('shortcut.gotoDashboard'), action: () => router.push('/'), group: t('shortcut.groupNavigation') }, // FIXED: 国际化
      { key: 'g m', description: t('shortcut.gotoMonitor'), action: () => router.push('/monitor'), group: t('shortcut.groupNavigation') }, // FIXED: 国际化
      { key: 'g c', description: t('shortcut.gotoDevices'), action: () => router.push('/devices'), group: t('shortcut.groupNavigation') }, // FIXED: 国际化
      { key: 'g a', description: t('shortcut.gotoAlarms'), action: () => router.push('/alarms'), group: t('shortcut.groupNavigation') }, // FIXED: 国际化
      { key: 'g r', description: t('shortcut.gotoRecords'), action: () => router.push('/cloud-records'), group: t('shortcut.groupNavigation') }, // FIXED: 国际化
      { key: 'g p', description: t('shortcut.gotoOps'), action: () => router.push('/ops'), group: t('shortcut.groupNavigation') }, // FIXED: 国际化
      { key: 'g u', description: t('shortcut.gotoUsers'), action: () => router.push('/users'), group: t('shortcut.groupNavigation') }, // FIXED: 国际化
      { key: 'g s', description: t('shortcut.gotoSettings'), action: () => router.push('/config-center'), group: t('shortcut.groupNavigation') }, // FIXED: 国际化
      { key: '?', description: t('shortcut.openHelp'), action: () => { showHelp.value = !showHelp.value }, group: t('shortcut.groupAction'), showInHelp: true }, // FIXED: 国际化
      { key: 'Ctrl+K', description: t('shortcut.openHelpPage'), action: () => router.push('/help'), group: t('shortcut.groupAction') }, // FIXED: 国际化
      { key: 'Escape', description: t('shortcut.closeDialog'), action: () => { if (showHelp.value) showHelp.value = false }, group: t('shortcut.groupAction'), showInHelp: true }, // FIXED: 国际化
      { key: 'r', description: t('shortcut.refreshPage'), action: () => window.location.reload(), group: t('shortcut.groupAction') }, // FIXED: 国际化
    ]
  }

  onMounted(() => {
    window.addEventListener('keydown', handleKeydown)
  })

  onUnmounted(() => {
    window.removeEventListener('keydown', handleKeydown)
    if (sequenceTimer) {
      clearTimeout(sequenceTimer)
    }
  })

  return {
    showHelp,
    registerHelpAction,
    getVisibleShortcuts,
    getShortcutsByGroup,
  }
}

export const useGlobalShortcutsState = () => {
  return {
    showHelp,
    registerHelpAction,
  }
}
