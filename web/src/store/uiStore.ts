import { create } from 'zustand'

export interface GenParams {
  num_ctx: number
  num_predict: number
  temperature: number
  top_p: number
}

const DEFAULT_GEN_PARAMS: GenParams = {
  num_ctx: 32768,
  num_predict: 0,  // 0 = sınırsız (cap gönderilmez, model EOS'a kadar üretir)
  temperature: 0.7,
  top_p: 0.9,
}

function loadGenParams(): GenParams {
  try {
    const raw = localStorage.getItem('genParams')
    if (raw) return { ...DEFAULT_GEN_PARAMS, ...JSON.parse(raw) }
  } catch {}
  return { ...DEFAULT_GEN_PARAMS }
}

interface UIState {
  sidebarOpen: boolean
  // Mobilde PanelLayout'un ana gezinme çekmecesi (Sohbet/Modeller/Ayarlar vb.).
  // Sohbet rotasında PanelLayout kendi üst çubuğunu göstermiyor (ChatPage tam
  // ekranı kullanıyor), o yüzden ChatPage'in kendi üst çubuğundan da bu
  // çekmeceyi açabilmesi için paylaşılan store'da tutuluyor.
  mainNavOpen: boolean
  commandPaletteOpen: boolean
  activeChatId: string | null
  setSidebarOpen: (v: boolean) => void
  toggleSidebar: () => void
  setMainNavOpen: (v: boolean) => void
  setCommandPaletteOpen: (v: boolean) => void
  setActiveChatId: (id: string | null) => void
  drafts: Record<string, string>
  setDraft: (chatId: string, text: string) => void
  getDraft: (chatId: string) => string
  globalMaxTokens: number
  setGlobalMaxTokens: (val: number) => void
  visionModel: string
  setVisionModel: (val: string) => void
  captionModel: string
  setCaptionModel: (val: string) => void
  injectedAttachment: any | null
  setInjectedAttachment: (val: any | null) => void
  genParams: GenParams
  setGenParams: (p: Partial<GenParams>) => void
  resetGenParams: () => void
}

export const useUIStore = create<UIState>((set, get) => ({
  sidebarOpen: window.innerWidth >= 1024,
  mainNavOpen: false,
  commandPaletteOpen: false,
  activeChatId: null,
  drafts: {},
  setSidebarOpen: (v) => set({ sidebarOpen: v }),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  setMainNavOpen: (v) => set({ mainNavOpen: v }),
  setCommandPaletteOpen: (v) => set({ commandPaletteOpen: v }),
  setActiveChatId: (id) => set({ activeChatId: id }),
  setDraft: (chatId, text) => set((s) => ({ drafts: { ...s.drafts, [chatId]: text } })),
  getDraft: (chatId) => get().drafts[chatId] || '',
  globalMaxTokens: parseInt(localStorage.getItem('globalMaxTokens') || '250000'),
  setGlobalMaxTokens: (v) => {
    localStorage.setItem('globalMaxTokens', v.toString())
    set({ globalMaxTokens: v })
  },
  visionModel: localStorage.getItem('visionModel') || '',
  setVisionModel: (v) => {
    localStorage.setItem('visionModel', v)
    set({ visionModel: v })
  },
  captionModel: localStorage.getItem('captionModel') || '',
  setCaptionModel: (v) => {
    localStorage.setItem('captionModel', v)
    set({ captionModel: v })
  },
  injectedAttachment: null,
  setInjectedAttachment: (val) => set({ injectedAttachment: val }),
  genParams: loadGenParams(),
  setGenParams: (p) => {
    const next = { ...get().genParams, ...p }
    localStorage.setItem('genParams', JSON.stringify(next))
    set({ genParams: next })
  },
  resetGenParams: () => {
    localStorage.setItem('genParams', JSON.stringify(DEFAULT_GEN_PARAMS))
    set({ genParams: { ...DEFAULT_GEN_PARAMS } })
  },
}))

export { DEFAULT_GEN_PARAMS }
