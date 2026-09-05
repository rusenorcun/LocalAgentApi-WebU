import { useState, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { motion, AnimatePresence } from 'framer-motion'
import { Plus, Search, Pin, PinOff, Pencil, Trash2, X, CheckSquare, MoreVertical, Archive, FolderInput, ChevronRight, ChevronDown, Download } from 'lucide-react'
import { getChats, createChat, patchChat, deleteChat } from '../../api/chats'
import { listSummaries, batchSummarize, injectSummary, deleteSummary } from '../../api/summaries'
import type { SummaryOut } from '../../api/summaries'
import { listProjects, addChatToProject } from '../../api/projects'
import type { ProjectOut } from '../../api/projects'
import { useUIStore } from '../../store/uiStore'
import type { ChatSummary } from '../../api/chats'

function groupChats(chats: ChatSummary[]) {
  const now = new Date()
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const yesterdayStart = todayStart - 86400000
  const weekStart = todayStart - 6 * 86400000

  const pinned = chats.filter((c) => c.pinned)
  const rest = chats.filter((c) => !c.pinned)

  const today: ChatSummary[] = []
  const yesterday: ChatSummary[] = []
  const thisWeek: ChatSummary[] = []
  const older: ChatSummary[] = []

  for (const c of rest) {
    const t = new Date(c.updated_at).getTime()
    if (t >= todayStart) today.push(c)
    else if (t >= yesterdayStart) yesterday.push(c)
    else if (t >= weekStart) thisWeek.push(c)
    else older.push(c)
  }
  return { pinned, today, yesterday, thisWeek, older }
}

import ProjectsPanel from './ProjectsPanel'

// ── Modül seviyesi bileşenler ────────────────────────────────────────────────
// ÖNEMLİ: Bunlar render İÇİNDE tanımlanmamalı; aksi halde her render'da yeni
// bileşen tipi oluşur, React tüm listeyi söküp yeniden kurar (giriş animasyonu
// her tuşta tekrar oynar — "menü yeniden yükleniyor" görüntüsü).

function SummaryItem({ s, chats, onInject, onDelete }: {
  s: SummaryOut
  chats: ChatSummary[]
  onInject: (chatId: string) => void
  onDelete: () => void
}) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [showChatPicker, setShowChatPicker] = useState(false)
  const btnRef = useRef<HTMLButtonElement>(null)
  const [menuStyle, setMenuStyle] = useState<React.CSSProperties>({})
  // Menü: overflow'lu listede kırpılmasın diye 'fixed'; altta yer yoksa yukarı açılır.
  const openMenu = () => {
    const el = btnRef.current
    if (el) {
      const r = el.getBoundingClientRect()
      const estH = 230  // menü + olası "Sohbete Aktar" alt listesi
      const right = Math.max(8, window.innerWidth - r.right)
      const openUp = r.bottom + estH > window.innerHeight
      setMenuStyle(openUp
        ? { position: 'fixed', bottom: window.innerHeight - r.top + 4, right }
        : { position: 'fixed', top: r.bottom + 4, right })
    }
    setShowChatPicker(false)
    setMenuOpen(v => !v)
  }
  const sourceCount = (() => { try { return JSON.parse(s.source_chat_ids).length } catch { return 1 } })()
  const date = new Date(s.created_at).toLocaleDateString('tr-TR', { day: 'numeric', month: 'short' })

  const downloadSummary = () => {
    const blob = new Blob([s.summary_text], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = (s.title || 'ozet').replace(/[\\/:*?"<>|]/g, '_') + '.md'
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="group relative flex items-start gap-1.5 px-2 py-1.5 rounded-lg transition-colors hover:bg-[var(--surface-2)]">
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium truncate" style={{ color: 'var(--text)' }}>{s.title}</p>
        <p className="text-[10px]" style={{ color: 'var(--text-3)' }}>{sourceCount} sohbet · {date}</p>
      </div>
      <div className="relative shrink-0">
        <button
          ref={btnRef}
          onClick={(e) => { e.stopPropagation(); openMenu() }}
          className="p-1 rounded opacity-0 group-hover:opacity-100 transition-opacity hover:bg-[var(--surface-3)]"
          style={{ color: 'var(--text-2)' }}
        >
          <MoreVertical size={13} />
        </button>
        {createPortal(
          <AnimatePresence>
            {menuOpen && (
            <>
              <div className="fixed inset-0 z-[100]" onClick={() => { setMenuOpen(false); setShowChatPicker(false) }} />
              <motion.div
                initial={{ opacity: 0, scale: 0.95, y: -6 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: -6 }}
                transition={{ duration: 0.12 }}
                className="w-56 py-1 rounded-xl shadow-lg border z-[101] overflow-y-auto"
                style={{ background: 'var(--surface)', borderColor: 'var(--border)', maxHeight: 'calc(100vh - 16px)', ...menuStyle }}
              >
                {/* Sohbete Aktar */}
                <div className="relative">
                  <button
                    onClick={(e) => { e.stopPropagation(); setShowChatPicker(v => !v) }}
                    className="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-[var(--surface-2)] transition-colors text-left"
                    style={{ color: 'var(--text)' }}
                  >
                    <Archive size={13} />
                    <span className="flex-1">Sohbete Aktar</span>
                    <ChevronRight size={11} />
                  </button>
                  {showChatPicker && (
                    <div
                      className="mt-1 w-full max-h-40 overflow-y-auto py-1 rounded-lg border"
                      style={{ background: 'var(--surface-2)', borderColor: 'var(--border)' }}
                    >
                      {chats.length === 0 && (
                        <p className="px-3 py-2 text-xs" style={{ color: 'var(--text-3)' }}>Sohbet yok</p>
                      )}
                      {chats.slice(0, 3).map(c => (
                        <button key={c.id}
                          onClick={(e) => { e.stopPropagation(); onInject(c.id); setMenuOpen(false); setShowChatPicker(false) }}
                          className="w-full flex items-start px-3 py-2 text-xs hover:bg-[var(--surface-2)] transition-colors text-left truncate"
                          style={{ color: 'var(--text)' }}
                        >
                          {c.title}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                {/* Sohbetin özetini indir */}
                <button
                  onClick={(e) => { e.stopPropagation(); downloadSummary(); setMenuOpen(false) }}
                  className="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-[var(--surface-2)] transition-colors text-left"
                  style={{ color: 'var(--text)' }}
                >
                  <Download size={13} />
                  Özeti indir
                </button>
                <div className="h-px mx-2 my-1" style={{ background: 'var(--border)' }} />
                {/* Sil */}
                <button
                  onClick={(e) => { e.stopPropagation(); onDelete(); setMenuOpen(false) }}
                  className="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-[var(--surface-2)] transition-colors text-left"
                  style={{ color: 'var(--error)' }}
                >
                  <Trash2 size={13} />
                  Sil
                </button>
              </motion.div>
            </>
            )}
          </AnimatePresence>,
          document.body,
        )}
      </div>
    </div>
  )
}

interface ChatItemProps {
  c: ChatSummary
  active: boolean
  renaming: boolean
  renameVal: string
  onRenameChange: (v: string) => void
  onRenameCommit: (c: ChatSummary, title: string) => void
  onRenameCancel: () => void
  onRenameStart: (c: ChatSummary) => void
  onOpen: (id: string) => void
  onPinToggle: (c: ChatSummary) => void
  onDelete: (c: ChatSummary) => void
  multiSelectMode?: boolean
  selected?: boolean
  onToggleSelect?: (id: string) => void
  onEnableMultiSelect?: () => void
  onCreateSummary?: (c: ChatSummary) => void
  projects?: ProjectOut[]
  onAddToProject?: (projectId: string, chatId: string) => void
}

function ChatItem({ c, active, renaming, renameVal, onRenameChange, onRenameCommit,
                    onRenameCancel, onRenameStart, onOpen, onPinToggle, onDelete,
                    multiSelectMode, selected, onToggleSelect, onEnableMultiSelect, onCreateSummary,
                    projects, onAddToProject }: ChatItemProps) {
  const { t } = useTranslation()
  const [menuOpen, setMenuOpen] = useState(false)
  const [showProjects, setShowProjects] = useState(false)
  if (renaming) {
    return (
      <div className="px-2 py-1">
        <input
          autoFocus value={renameVal}
          onChange={(e) => onRenameChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') onRenameCommit(c, renameVal)
            if (e.key === 'Escape') onRenameCancel()
          }}
          onBlur={onRenameCancel}
          className="w-full px-2 py-1 text-sm rounded-lg"
          style={{ background: 'var(--surface-2)', color: 'var(--text)', border: '1px solid var(--accent)', outline: 'none' }}
        />
      </div>
    )
  }
  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      className="group relative flex items-center px-2 py-2 rounded-xl cursor-pointer transition-colors"
      style={{
        background: selected ? 'color-mix(in srgb, var(--accent) 22%, transparent)' : (active ? 'var(--accent-soft)' : 'transparent'),
        color: active || selected ? 'var(--text)' : 'var(--text-2)',
      }}
      onClick={() => {
        if (multiSelectMode && onToggleSelect) onToggleSelect(c.id)
        else onOpen(c.id)
      }}
    >
      {multiSelectMode && (
        <div className="mr-2 flex items-center justify-center shrink-0 w-4 h-4 rounded border"
             style={{ borderColor: selected ? 'var(--accent)' : 'var(--border)', background: selected ? 'var(--accent)' : 'transparent' }}>
          {selected && <div className="w-2 h-2 bg-[var(--surface)] rounded-sm" />}
        </div>
      )}
      {!multiSelectMode && c.pinned && <Pin size={12} className="mr-1.5 shrink-0" style={{ color: 'var(--accent)' }} />}
      <span className="text-sm truncate flex-1">{c.title}</span>
      {!multiSelectMode && (
        <div className="relative hidden group-hover:flex items-center ml-1">
          <button onClick={(e) => { e.stopPropagation(); setMenuOpen(!menuOpen) }}
            className="p-1 rounded hover:bg-[var(--surface-2)] transition-colors" title="Daha fazla">
            <MoreVertical size={14} style={{ color: 'var(--text-2)' }} />
          </button>

          <AnimatePresence>
            {menuOpen && (
              <>
                <div className="fixed inset-0 z-40" onClick={(e) => { e.stopPropagation(); setMenuOpen(false) }} />
                <motion.div
                  initial={{ opacity: 0, scale: 0.95, y: -10 }}
                  animate={{ opacity: 1, scale: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.95, y: -10 }}
                  transition={{ duration: 0.15 }}
                  className="absolute right-0 top-6 w-48 py-1 rounded-xl shadow-lg border z-50 flex flex-col"
                  style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
                >
                  {onCreateSummary && (
                    <button onClick={(e) => { e.stopPropagation(); setMenuOpen(false); onCreateSummary(c) }}
                      className="flex items-center gap-2 px-3 py-2 text-xs hover:bg-[var(--surface-2)] transition-colors w-full text-left"
                      style={{ color: 'var(--text)' }}>
                      <><Archive size={14} /> {t('chat.sidebar.extractSummary')}</>
                    </button>
                  )}
                  {onEnableMultiSelect && (
                    <button onClick={(e) => { e.stopPropagation(); setMenuOpen(false); onEnableMultiSelect(); if(onToggleSelect) onToggleSelect(c.id); }}
                      className="flex items-center gap-2 px-3 py-2 text-xs hover:bg-[var(--surface-2)] transition-colors w-full text-left"
                      style={{ color: 'var(--text)' }}>
                      <><CheckSquare size={14} /> {t('chat.sidebar.select')}</>
                    </button>
                  )}
                  <div className="h-px w-full my-1" style={{ background: 'var(--border)' }} />
                  <button onClick={(e) => { e.stopPropagation(); setMenuOpen(false); onPinToggle(c) }}
                    className="flex items-center gap-2 px-3 py-2 text-xs hover:bg-[var(--surface-2)] transition-colors w-full text-left"
                    style={{ color: 'var(--text)' }}>
                    {c.pinned ? <PinOff size={14} /> : <Pin size={14} />} {c.pinned ? 'Sabitlemeyi Kaldır' : 'Sabitle'}
                  </button>
                  <button onClick={(e) => { e.stopPropagation(); setMenuOpen(false); onRenameStart(c) }}
                    className="flex items-center gap-2 px-3 py-2 text-xs hover:bg-[var(--surface-2)] transition-colors w-full text-left"
                    style={{ color: 'var(--text)' }}>
                    <Pencil size={14} /> Yeniden Adlandır
                  </button>
                  {onAddToProject && projects && projects.length > 0 && (
                    <div className="relative">
                      <button
                        onClick={(e) => { e.stopPropagation(); setShowProjects(!showProjects) }}
                        className="flex items-center gap-2 px-3 py-2 text-xs hover:bg-[var(--surface-2)] transition-colors w-full text-left"
                        style={{ color: 'var(--text)' }}>
                        <><FolderInput size={14} /> {t('chat.sidebar.moveToProject')}</>
                        <ChevronRight size={12} className="ml-auto" />
                      </button>
                      {showProjects && (
                        <div className="absolute left-full top-0 ml-1 w-44 py-1 rounded-xl shadow-lg border z-50"
                             style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}>
                          {projects.map(p => (
                            <button key={p.id}
                              onClick={(e) => {
                                e.stopPropagation()
                                onAddToProject(p.id, c.id)
                                setShowProjects(false)
                                setMenuOpen(false)
                              }}
                              className="flex items-center gap-2 px-3 py-2 text-xs hover:bg-[var(--surface-2)] transition-colors w-full text-left truncate"
                              style={{ color: 'var(--text)' }}>
                              {p.name}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                  <button onClick={(e) => { e.stopPropagation(); setMenuOpen(false); onDelete(c) }}
                    className="flex items-center gap-2 px-3 py-2 text-xs hover:bg-[var(--surface-2)] transition-colors w-full text-left"
                    style={{ color: 'var(--error)' }}>
                    <Trash2 size={14} /> Sil
                  </button>
                </motion.div>
              </>
            )}
          </AnimatePresence>
        </div>
      )}
    </motion.div>
  )
}

function Group({ label, items, render }: {
  label: string
  items: ChatSummary[]
  render: (c: ChatSummary) => ReactNode
}) {
  if (!items.length) return null
  return (
    <div className="mb-2">
      <p className="px-2 py-1 font-semibold uppercase"
         style={{ color: 'var(--text-3)', fontSize: '10.5px', letterSpacing: '.07em' }}>
        {label}
      </p>
      <AnimatePresence>
        {items.map((c) => render(c))}
      </AnimatePresence>
    </div>
  )
}

export default function Sidebar({ fullHeight = false }: { fullHeight?: boolean }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { chatId } = useParams<{ chatId: string }>()
  const qc = useQueryClient()
  // Seçici (selector) abonelik: drafts gibi alakasız store güncellemeleri
  // (Composer'a yazılan her harf!) bu bileşeni render ETMEMELİ.
  const setInjectedAttachment = useUIStore((s) => s.setInjectedAttachment)

  const [search, setSearch] = useState('')
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameVal, setRenameVal] = useState('')
  const [undoChat, setUndoChat] = useState<ChatSummary | null>(null)
  const [summariesOpen, setSummariesOpen] = useState(true)

  const [multiSelectMode, setMultiSelectMode] = useState(false)
  const [selectedChats, setSelectedChats] = useState<Set<string>>(new Set())

  const { data } = useQuery({ queryKey: ['chats'], queryFn: () => getChats().then((r) => r.data.chats) })
  const chats = data || []

  const { data: summariesData } = useQuery({ queryKey: ['summaries'], queryFn: () => listSummaries().then(r => r.data) })
  const summaries = summariesData || []

  const { data: projectsData } = useQuery({ queryKey: ['projects'], queryFn: () => listProjects().then(r => r.data) })
  const projects = projectsData || []

  const filtered = search
    ? chats.filter((c) => c.title.toLowerCase().includes(search.toLowerCase()))
    : chats

  const createMut = useMutation({
    mutationFn: () => createChat(t('chat.newChat')).then((r) => r.data),
    onSuccess: (c) => { qc.invalidateQueries({ queryKey: ['chats'] }); navigate(`/chat/${c.id}`) },
  })

  const patchMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<ChatSummary> }) =>
      patchChat(id, data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['chats'] }),
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteChat(id),
    onSuccess: (_, id) => {
      qc.invalidateQueries({ queryKey: ['chats'] })
      if (chatId === id) navigate('/chat')
    },
  })

  const batchSumMut = useMutation({
    mutationFn: (ids: string[]) => batchSummarize(ids),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['summaries'] })
      await qc.refetchQueries({ queryKey: ['summaries'] })
      setSummariesOpen(true)
      setMultiSelectMode(false)
      setSelectedChats(new Set())
    },
    onError: (e: any) => {
      alert('Özetleme başarısız: ' + (e?.response?.data?.detail || e?.message || 'Sunucu hatası. Backend yeniden başlatıldı mı?'))
    }
  })

  const injectSumMut = useMutation({
    mutationFn: ({ chatId, summaryId }: { chatId: string, summaryId: string }) => injectSummary(chatId, summaryId),
    onSuccess: (res, { chatId }) => {
      setInjectedAttachment(res.data)
      qc.invalidateQueries({ queryKey: ['chat', chatId] })
    }
  })

  const deleteSumMut = useMutation({
    mutationFn: (id: string) => deleteSummary(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['summaries'] }),
    onError: (e: any) => alert('Özet silinemedi: ' + (e?.response?.data?.detail || e?.message || 'Hata'))
  })

  const addToProjectMut = useMutation({
    mutationFn: ({ projectId, chatId }: { projectId: string; chatId: string }) =>
      addChatToProject(projectId, chatId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['projects'] }),
  })

  const handleDelete = (c: ChatSummary) => {
    setUndoChat(c)
    deleteMut.mutate(c.id)
    setTimeout(() => setUndoChat(null), 5000)
  }

  const groups = groupChats(filtered)

  const renderItem = (c: ChatSummary) => (
    <ChatItem
      key={c.id}
      c={c}
      active={chatId === c.id}
      renaming={renamingId === c.id}
      renameVal={renameVal}
      onRenameChange={setRenameVal}
      onRenameCommit={(cc, title) => { patchMut.mutate({ id: cc.id, data: { title } }); setRenamingId(null) }}
      onRenameCancel={() => setRenamingId(null)}
      onRenameStart={(cc) => { setRenamingId(cc.id); setRenameVal(cc.title) }}
      onOpen={(id) => navigate(`/chat/${id}`)}
      onPinToggle={(cc) => patchMut.mutate({ id: cc.id, data: { pinned: !cc.pinned } })}
      onDelete={handleDelete}
      multiSelectMode={multiSelectMode}
      selected={selectedChats.has(c.id)}
      onToggleSelect={(id) => {
        const next = new Set(selectedChats)
        if (next.has(id)) next.delete(id)
        else next.add(id)
        setSelectedChats(next)
      }}
      onEnableMultiSelect={() => setMultiSelectMode(true)}
      onCreateSummary={(cc) => {
        batchSumMut.mutate([cc.id])
      }}
      projects={projects}
      onAddToProject={(projectId, chatId) => addToProjectMut.mutate({ projectId, chatId })}
    />
  )

  return (
    // NOT: Bu artık AYRI bir panel/kolon DEĞİL — PanelLayout'un tek gezinme
    // rayının İÇİNDE, "Sohbet" düğmesinin hemen altına gömülü bir bölüm.
    // Eskiden ChatPage tek başına tüm sayfaydı ve bu bileşen kendi genişliğine
    // sahip bağımsız bir <aside> idi; o yüzden yan yana iki panel gibi
    // görünüyordu. Artık dış sarmalayıcısı yok — PanelLayout onu nav içine
    // doğrudan yerleştiriyor, tek bir birleşik panel hissi veriyor.
    <div className={`flex flex-col gap-0.5 overflow-y-auto pr-0.5 -mr-0.5 ${fullHeight ? 'flex-1 min-h-0' : 'max-h-[46vh]'}`}>
        {/* Header */}
        <div className="flex items-center justify-between px-1 py-1.5 shrink-0">
          {multiSelectMode ? (
            <div className="flex w-full items-center justify-between animate-in fade-in slide-in-from-top-2 duration-200">
              <span className="text-sm font-medium" style={{ color: 'var(--text)' }}>
                {t('chat.sidebar.selected', { count: selectedChats.size })}
              </span>
              <div className="flex items-center gap-2">
                <button
                  disabled={selectedChats.size === 0 || batchSumMut.isPending}
                  onClick={() => batchSumMut.mutate(Array.from(selectedChats))}
                  className="text-xs px-3 py-1.5 rounded font-medium disabled:opacity-50 flex items-center gap-1.5"
                  style={{ background: 'var(--grad)', color: '#fff' }}
                >
                  {batchSumMut.isPending ? 'Özetleniyor…' : (
                    <><Archive size={14} /> {t('chat.sidebar.summarizeAll')}</>
                  )}
                </button>
                <button onClick={() => { setMultiSelectMode(false); setSelectedChats(new Set()) }}
                  className="p-1.5 rounded-lg hover:bg-[var(--surface-2)] transition-colors"
                  style={{ color: 'var(--text-3)' }}>
                  <X size={16} />
                </button>
              </div>
            </div>
          ) : (
            <div className="flex w-full items-center justify-between animate-in fade-in duration-200">
              {/* NOT: Burada eskiden ayrı bir logo/marka başlığı vardı ("LocalAgent"),
                  bu da bu listenin PanelLayout'un kendi rayından bağımsız ayrı bir
                  panelmiş gibi görünmesine sebep oluyordu (iki logo yan yana). Marka
                  zaten solda PanelLayout rayında sürekli görünür durumda; burada
                  yalnızca bu alt bölümün adı yeterli — tek, birleşik panel hissi verir. */}
              <span className="text-sm font-semibold px-1" style={{ color: 'var(--text)' }}>
                {t('chat.sidebar.title', 'Sohbetler')}
              </span>
              <div className="flex gap-1">
                <button
                  onClick={() => {
                    setMultiSelectMode(!multiSelectMode)
                    setSelectedChats(new Set())
                  }}
                  className="p-1.5 rounded-lg transition-colors hover:bg-[var(--surface-2)]"
                  style={{ color: multiSelectMode ? 'var(--accent)' : 'var(--text-3)' }}
                  title={t('chat.sidebar.multiSelect')}
                >
                  <CheckSquare size={18} />
                </button>
                <button
                  onClick={() => createMut.mutate()}
                  className="p-1.5 rounded-lg transition-colors hover:bg-[var(--surface-2)]"
                  style={{ color: 'var(--text-3)' }}
                  title={t('chat.newChat')}
                >
                  <Plus size={18} />
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Arama */}
        <div className="px-3 pt-2 pb-1 shrink-0">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl"
               style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}>
            <Search size={14} style={{ color: 'var(--text-3)' }} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t('chat.search')}
              className="flex-1 bg-transparent text-sm outline-none"
              style={{ color: 'var(--text)' }}
            />
            {search && (
              <button onClick={() => setSearch('')} style={{ color: 'var(--text-3)' }}>
                <X size={12} />
              </button>
            )}
          </div>
        </div>

        {/* Projeler */}
        <ProjectsPanel />

        {/* Sohbet listesi */}
        <div className="flex-1 overflow-y-auto px-2 py-1">
          <Group label={t('chat.groups.pinned')} items={groups.pinned} render={renderItem} />
          <Group label={t('chat.groups.today')} items={groups.today} render={renderItem} />
          <Group label={t('chat.groups.yesterday')} items={groups.yesterday} render={renderItem} />
          <Group label={t('chat.groups.thisWeek')} items={groups.thisWeek} render={renderItem} />
          <Group label={t('chat.groups.older')} items={groups.older} render={renderItem} />
          {filtered.length === 0 && (
            <p className="px-4 py-8 text-center text-sm" style={{ color: 'var(--text-3)' }}>
              {search ? t('chat.noResults') : t('chat.noChats')}
            </p>
          )}
        </div>

        {/* Özetler bölümü */}
        {summaries.length > 0 && (
          <div className="shrink-0 border-t px-2 py-2" style={{ borderColor: 'var(--border)' }}>
            <button
              onClick={() => setSummariesOpen(v => !v)}
              className="flex w-full items-center justify-between px-2 py-1 rounded-lg hover:bg-[var(--surface-2)] transition-colors"
            >
              <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-3)' }}>
                {t('chat.summaries.title')} ({summaries.length})
              </span>
              {summariesOpen
                ? <ChevronDown size={13} style={{ color: 'var(--text-3)' }} />
                : <ChevronRight size={13} style={{ color: 'var(--text-3)' }} />}
            </button>
            <AnimatePresence>
              {summariesOpen && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="overflow-hidden"
                >
                  <div className="max-h-[60vh] min-h-[140px] overflow-y-auto space-y-0.5 mt-1">
                    {summaries.map((s: SummaryOut) => (
                      <SummaryItem
                        key={s.id}
                        s={s}
                        chats={chats}
                        onInject={(cid) => injectSumMut.mutate({ chatId: cid, summaryId: s.id })}
                        onDelete={() => deleteSumMut.mutate(s.id)}
                      />
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}

        {/* Undo bildirimi */}
        <AnimatePresence>
          {undoChat && (
            <motion.div
              initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 10 }}
              className="mx-2 mb-2 px-3 py-2 rounded-xl flex items-center justify-between text-xs"
              style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', color: 'var(--text-2)' }}
            >
              <span>{t('chat.deleted')}</span>
              <button
                onClick={() => {
                  patchMut.mutate({ id: undoChat.id, data: {} })
                  setUndoChat(null)
                }}
                className="font-medium hover:underline"
                style={{ color: 'var(--accent)' }}
              >
                {t('chat.undo')}
              </button>
            </motion.div>
          )}
        </AnimatePresence>

    </div>
  )
}
