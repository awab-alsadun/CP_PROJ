import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import en from './locales/en.json'
import ar from './locales/ar.json'

const STORAGE_KEY = 'invox_language'

export function getStoredLanguage() {
  return localStorage.getItem(STORAGE_KEY) || 'en'
}

export function setStoredLanguage(lang) {
  localStorage.setItem(STORAGE_KEY, lang)
}

export function getDirection() {
  return document.documentElement.dir === 'rtl' ? 'rtl' : 'ltr'
}

i18n
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      ar: { translation: ar },
    },
    lng: getStoredLanguage(),
    fallbackLng: 'en',
    interpolation: { escapeValue: false },
  })

export default i18n
