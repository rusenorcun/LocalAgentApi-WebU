import { useEffect } from 'react'
import { useAuthStore } from '../store/authStore'
import { updatePreferences } from '../api/auth'
// Kod bloğu vurgulama teması (highlight.js) sabit "dark" olarak import edilmişti —
// bu yüzden açık temada kod blokları hep koyu kalıyordu ("ışık modu çalışmıyor"
// şikayetinin bir parçası). Artık iki temayı da ham CSS metni olarak alıp aktif
// temaya göre tek bir <style> etiketine basıyoruz.
import hljsLight from 'highlight.js/styles/github.css?raw'
import hljsDark from 'highlight.js/styles/github-dark.css?raw'

let hljsStyleEl: HTMLStyleElement | null = null
function getHljsStyleEl(): HTMLStyleElement {
  if (!hljsStyleEl) {
    hljsStyleEl = document.createElement('style')
    hljsStyleEl.id = 'hljs-theme'
    document.head.appendChild(hljsStyleEl)
  }
  return hljsStyleEl
}

export function useTheme() {
  const { theme, setPreferences } = useAuthStore()

  useEffect(() => {
    const root = document.documentElement
    const apply = (isDark: boolean) => {
      root.classList.toggle('dark', isDark)
      getHljsStyleEl().textContent = isDark ? hljsDark : hljsLight
    }
    const resolve = () => {
      if (theme === 'dark') apply(true)
      else if (theme === 'light') apply(false)
      else apply(window.matchMedia('(prefers-color-scheme: dark)').matches)
    }
    resolve()

    if (theme === 'system') {
      const mq = window.matchMedia('(prefers-color-scheme: dark)')
      const handler = () => resolve()
      mq.addEventListener('change', handler)
      return () => mq.removeEventListener('change', handler)
    }
  }, [theme])

  const setTheme = (t: string) => {
    setPreferences(t, undefined)
    updatePreferences({ theme: t }).catch(() => {})
  }

  return { theme, setTheme }
}
