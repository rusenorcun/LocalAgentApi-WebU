import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Search, MessageSquarePlus, Sun, Moon, Hash } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { useUIStore } from '../../store/uiStore'
import { useAuthStore } from '../../store/authStore'
import { useQuery } from '@tanstack/react-query'
import { getChats, createChat } from '../../api/chats'

export default function CommandPalette() {
  const { t } = useTranslation()
  const commandPaletteOpen = useUIStore((s) => s.commandPaletteOpen)
  const setCommandPaletteOpen = useUIStore((s) => s.setCommandPaletteOpen)
  const setActiveChatId = useUIStore((s) => s.setActiveChatId)
  const { theme, setTheme } = useAuthStore()
  const navigate = useNavigate()
  const inputRef = useRef<HTMLInputElement>(null)
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(0)

  // DİKKAT: ['chats'] anahtarı Sidebar ile paylaşılıyor — queryFn ŞEKLİ AYNI OLMALI
  // (dizi). Farklı şekil yazılırsa Sidebar'daki .filter çağrısı çöker.
  const { data } = useQuery({
    queryKey: ['chats'],
    queryFn: () => getChats().then((r) => r.data.chats),
    enabled: commandPaletteOpen,
  })
  const chats = data ?? []

  // Ctrl+K aç/kapat
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault()
        setCommandPaletteOpen(!commandPaletteOpen)
      }
      if (e.key === 'Escape') setCommandPaletteOpen(false)
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [commandPaletteOpen, setCommandPaletteOpen])

  useEffect(() => {
    if (commandPaletteOpen) { setQuery(''); setSelected(0); setTimeout(() => inputRef.current?.focus(), 50) }
  }, [commandPaletteOpen])

  const staticActions = [
    {
      id: 'new', icon: <MessageSquarePlus size={16} />, label: t('palette.newChat'),
      action: async () => {
        const res = await createChat(t('chat.newChat'))
        const id = res.data.id
        setActiveChatId(id); navigate(`/chat/${id}`)
        setCommandPaletteOpen(false)
      }
    },
    {
      id: 'theme', icon: theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />,
      label: theme === 'dark' ? t('palette.lightMode') : t('palette.darkMode'),
      action: () => { setTheme(theme === 'dark' ? 'light' : 'dark'); setCommandPaletteOpen(false) }
    },
  ]

  const filteredChats = query
    ? chats.filter((c: any) => c.title.toLowerCase().includes(query.toLowerCase())).slice(0, 6)
    : chats.slice(0, 6)

  const items = [
    ...staticActions,
    ...filteredChats.map((c: any) => ({
      id: c.id, icon: <Hash size={16} />, label: c.title,
      action: () => { setActiveChatId(c.id); navigate(`/chat/${c.id}`); setCommandPaletteOpen(false) }
    })),
  ]

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setSelected(s => Math.min(s + 1, items.length - 1)) }
    if (e.key === 'ArrowUp') { e.preventDefault(); setSelected(s => Math.max(s - 1, 0)) }
    if (e.key === 'Enter') { e.preventDefault(); items[selected]?.action() }
  }

  return (
    <AnimatePresence>
      {commandPaletteOpen && (
        <>
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-40" style={{ background: 'rgba(0,0,0,0.4)' }}
            onClick={() => setCommandPaletteOpen(false)} />
          <motion.div initial={{ opacity: 0, scale: 0.96, y: -12 }} animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: -12 }} transition={{ duration: 0.15 }}
            className="fixed top-24 left-1/2 -translate-x-1/2 z-50 w-full max-w-lg rounded-2xl overflow-hidden"
            style={{ background: 'var(--surface)', border: '1px solid var(--border)', boxShadow: 'var(--shadow-xl)' }}>
            {/* Arama */}
            <div className="flex items-center gap-3 px-4 py-3" style={{ borderBottom: '1px solid var(--border)' }}>
              <Search size={16} style={{ color: 'var(--text-3)' }} />
              <input ref={inputRef} value={query} onChange={e => { setQuery(e.target.value); setSelected(0) }}
                onKeyDown={onKeyDown} placeholder={t('palette.placeholder')}
                className="flex-1 bg-transparent text-sm outline-none"
                style={{ color: 'var(--text)' }} />
              <kbd className="text-xs px-1.5 py-0.5 rounded" style={{ background: 'var(--surface-2)', color: 'var(--text-3)' }}>Esc</kbd>
            </div>
            {/* Sonuçlar */}
            <div className="p-2 max-h-80 overflow-y-auto">
              {items.map((item, idx) => (
                <button key={item.id} onClick={item.action}
                  onMouseEnter={() => setSelected(idx)}
                  className="w-full flex items-center gap-3 px-3 py-2 rounded-xl text-sm text-left transition-colors"
                  style={{ background: idx === selected ? 'var(--surface-2)' : undefined, color: 'var(--text)' }}>
                  <span style={{ color: 'var(--text-3)' }}>{item.icon}</span>
                  <span className="truncate">{item.label}</span>
                </button>
              ))}
              {items.length === 0 && (
                <p className="text-center py-6 text-sm" style={{ color: 'var(--text-3)' }}>{t('palette.noResults')}</p>
              )}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
