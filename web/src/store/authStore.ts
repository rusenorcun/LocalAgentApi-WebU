import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface AuthState {
  accessToken: string | null
  username: string | null
  role: string | null
  theme: string
  lang: string
  setTokens: (token: string, username: string, role: string) => void
  setPreferences: (theme?: string, lang?: string) => void
  setTheme: (theme: string) => void
  setLang: (lang: string) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      username: null,
      role: null,
      theme: 'system',
      lang: 'tr',
      setTokens: (accessToken, username, role) => set({ accessToken, username, role }),
      setPreferences: (theme, lang) => {
        if (theme) set({ theme })
        if (lang) set({ lang })
      },
      setTheme: (theme) => set({ theme }),
      setLang: (lang) => set({ lang }),
      logout: () => set({ accessToken: null, username: null, role: null }),
    }),
    // GÜVENLİK (G2): accessToken/username/role localStorage'a YAZILMAZ —
    // XSS bir token çalamasın. Token yalnız bellekte yaşar; sayfa yenilenince
    // httpOnly refresh cookie ile sessizce yeniden alınır (App.tsx RequireAuth).
    { name: 'auth-storage', partialize: (s) => ({ theme: s.theme, lang: s.lang }) }
  )
)
