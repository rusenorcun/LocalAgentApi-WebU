import { useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Upload, Trash2, FileText, Loader2, CheckCircle, AlertCircle, ArrowRightFromLine } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { listDocuments, uploadDocument, deleteDocument, injectDocument } from '../../api/rag'
import { listSummaries, injectSummary, deleteSummary } from '../../api/summaries'
import { useUIStore } from '../../store/uiStore'

export default function KnowledgeBase() {
  const { chatId } = useParams<{ chatId?: string }>()
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)
  const setInjectedAttachment = useUIStore(s => s.setInjectedAttachment)

  const { data } = useQuery({
    queryKey: ['rag', 'documents'],
    queryFn: () => listDocuments().then(r => r.data),
    refetchInterval: (query: any) => {
      const docs: any[] = query.state?.data?.documents ?? []
      return docs.some((d: any) => d.status.startsWith('processing')) ? 3000 : false
    },
  })

  const upload = useMutation({
    mutationFn: (file: File) => uploadDocument(file),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rag', 'documents'] }),
  })

  const remove = useMutation({
    mutationFn: (id: number) => deleteDocument(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rag', 'documents'] }),
  })

  // Özetler
  const { data: sumData } = useQuery({
    queryKey: ['summaries'],
    queryFn: () => listSummaries().then(r => r.data)
  })
  const summaries = sumData || []

  const deleteSumMut = useMutation({
    mutationFn: (id: string) => deleteSummary(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['summaries'] })
  })

  const injectSumMut = useMutation({
    mutationFn: ({ chatId, summaryId }: { chatId: string, summaryId: string }) => injectSummary(chatId, summaryId),
    onSuccess: (res, v) => {
      setInjectedAttachment(res.data)
      qc.invalidateQueries({ queryKey: ['chat', v.chatId] })
    }
  })

  const injectDocMut = useMutation({
    mutationFn: ({ chatId, docId }: { chatId: string, docId: number }) => injectDocument(chatId, docId),
    onSuccess: (res, v) => {
      setInjectedAttachment(res.data)
      qc.invalidateQueries({ queryKey: ['chat', v.chatId] })
    }
  })

  const docs: any[] = data?.documents ?? []

  const handleFiles = (files: FileList | null) => {
    if (!files) return
    Array.from(files).forEach(f => upload.mutate(f))
  }

  return (
    <div className="p-4 flex flex-col gap-6">

      {/* Özetler Bölümü (Üstte) */}
      {summaries.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <p className="text-xs font-semibold tracking-wide mb-1" style={{ color: 'var(--text-3)' }}>ÖZETLER</p>
          <AnimatePresence initial={false}>
            {summaries.map(s => (
              <motion.div key={s.id}
                initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, height: 0 }}
                className="flex items-center gap-2 px-3 py-2 rounded-xl group transition-colors"
                style={{ background: 'var(--surface-2)' }}>
                <FileText size={14} className="shrink-0" style={{ color: 'var(--accent)' }} />
                <div className="flex-1 min-w-0 flex flex-col">
                  <span className="text-xs font-medium truncate" style={{ color: 'var(--text-2)' }}>{s.title}</span>
                  <span className="text-[9px]" style={{ color: 'var(--text-3)' }}>{new Date(s.created_at).toLocaleDateString()}</span>
                </div>
                {chatId && (
                  <button onClick={() => injectSumMut.mutate({ chatId, summaryId: s.id })}
                    disabled={injectSumMut.isPending}
                    className="opacity-0 group-hover:opacity-100 p-1.5 rounded transition-opacity"
                    style={{ color: 'var(--text-2)', background: 'var(--surface)' }} title="Sohbete Aktar">
                    <ArrowRightFromLine size={13} />
                  </button>
                )}
                <button onClick={() => deleteSumMut.mutate(s.id)}
                  className="opacity-0 group-hover:opacity-100 p-1.5 rounded transition-opacity"
                  style={{ color: 'var(--error)' }} title="Sil">
                  <Trash2 size={13} />
                </button>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}

      {/* Bilgi Tabanı Bölümü (Altta) */}
      <div className="flex flex-col gap-1.5">
        <p className="text-xs font-semibold uppercase tracking-widest mb-1" style={{ color: 'var(--text-3)' }}>
          Bilgi Tabanı
        </p>

        {/* Yükleme alanı */}
        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => { e.preventDefault(); setDragOver(false); handleFiles(e.dataTransfer.files) }}
          onClick={() => fileRef.current?.click()}
          className="flex flex-col items-center justify-center gap-2 py-4 rounded-xl cursor-pointer transition-colors mb-1"
          style={{
            border: `2px dashed ${dragOver ? 'var(--accent)' : 'var(--border)'}`,
            background: dragOver ? 'color-mix(in srgb, var(--accent) 8%, transparent)' : 'var(--surface-2)',
          }}>
          <Upload size={20} style={{ color: dragOver ? 'var(--accent)' : 'var(--text-3)' }} />
          <p className="text-xs text-center" style={{ color: 'var(--text-3)' }}>
            Dosya yükle veya sürükle
          </p>
          <input ref={fileRef} type="file" multiple className="hidden"
            onChange={(e) => handleFiles(e.target.files)} />
        </div>

        {docs.some(d => d.status.startsWith('processing')) && (
          <p className="text-[10px] text-center mb-3 leading-snug px-1" style={{ color: 'var(--warning, #eab308)' }}>
            (Yüklenen belgelerde en fazla 10 görsel işlenmektedir. Çok fazla görsel içeren belgelerin işleme adımları uzun sürebilir lütfen bekleyiniz ve bir hata ile karşılaşırsanız sunucu sahibi ile iletişime geçiniz.)
          </p>
        )}

        {/* Belge listesi */}
        <div className="flex flex-col gap-1.5">
          <AnimatePresence initial={false}>
            {docs.map(doc => (
              <motion.div key={doc.id}
                initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, height: 0 }}
                className="flex items-center gap-2 px-3 py-2 rounded-xl group"
                style={{ background: 'var(--surface-2)' }}>
                <StatusIcon status={doc.status} />
                <span className="flex-1 text-xs truncate" style={{ color: 'var(--text-2)' }}>
                  {doc.name}
                </span>
                <span className="text-[10px] shrink-0" style={{ color: 'var(--text-3)' }}>
                  {formatSize(doc.size)}
                </span>
                {chatId && !doc.status.startsWith('processing') && (
                  <button onClick={() => injectDocMut.mutate({ chatId, docId: doc.id })}
                    disabled={injectDocMut.isPending}
                    className="opacity-0 group-hover:opacity-100 p-1 rounded transition-opacity"
                    style={{ color: 'var(--text-2)', background: 'var(--surface)' }} title="Sohbete Aktar">
                    <ArrowRightFromLine size={13} />
                  </button>
                )}
                <button onClick={() => remove.mutate(doc.id)}
                  className="opacity-0 group-hover:opacity-100 p-1 rounded transition-opacity ml-1"
                  style={{ color: 'var(--error)' }} title="Sil">
                  <Trash2 size={12} />
                </button>
              </motion.div>
            ))}
          </AnimatePresence>
          {docs.length === 0 && (
            <p className="text-xs text-center py-2" style={{ color: 'var(--text-3)' }}>Henüz içerik yok</p>
          )}
        </div>
      </div>
    </div>
  )
}

function StatusIcon({ status }: { status: string }) {
  if (status.startsWith('processing')) {
    let title = 'İşleniyor...'
    if (status === 'processing_text') title = 'Metin ayrıştırılıyor...'
    else if (status === 'processing_images') title = 'Görseller yorumlanıyor...'
    else if (status === 'processing_embeddings') title = 'Vektörler oluşturuluyor...'
    return <span title={title} className="shrink-0 flex"><Loader2 size={14} className="animate-spin" style={{ color: 'var(--accent)' }} /></span>
  }
  if (status === 'ready_warning_images') return <span title="İlk 10 görsel veya PDF sayfası işlendi, diğerleri atlandı." className="shrink-0 flex"><CheckCircle size={14} style={{ color: 'var(--success)' }} /></span>
  if (status === 'ready') return <span title="Hazır" className="shrink-0 flex"><CheckCircle size={14} style={{ color: 'var(--success)' }} /></span>
  if (status === 'error') return <span title="Hata oluştu" className="shrink-0 flex"><AlertCircle size={14} style={{ color: 'var(--error)' }} /></span>
  return <span className="shrink-0 flex"><FileText size={14} style={{ color: 'var(--text-3)' }} /></span>
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`
}
