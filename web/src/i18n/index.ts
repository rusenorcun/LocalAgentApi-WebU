import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import tr from './locales/tr.json'
import en from './locales/en.json'

// Kayıtlı dil zustand persist deposunda (auth-storage) tutulur.
// NOT: önceki sürümde `a || b ? 'tr' : 'en'` öncelik hatası vardı —
// her durumda 'tr' seçiliyordu.
function savedLangFromStore(): string | null {
  try {
    const s = JSON.parse(localStorage.getItem('auth-storage') || '{}')
    const lang = s?.state?.lang
    return lang === 'tr' || lang === 'en' ? lang : null
  } catch {
    return null
  }
}
const savedLang = savedLangFromStore() || (navigator.language.startsWith('tr') ? 'tr' : 'en')

i18n.use(initReactI18next).init({
  resources: { tr: { translation: tr }, en: { translation: en } },
  lng: savedLang as string,
  fallbackLng: 'tr',
  interpolation: { escapeValue: false },
})

export default i18n
