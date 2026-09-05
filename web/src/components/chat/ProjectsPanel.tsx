import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { FolderPlus, Folder, ChevronDown, ChevronRight, Trash2, Pencil, Check, X } from 'lucide-react'
import {
  listProjects, createProject, updateProject, deleteProject,
} from '../../api/projects'
import type { ProjectOut } from '../../api/projects'

export default function ProjectsPanel() {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editVal, setEditVal] = useState('')

  const { data: projects = [] } = useQuery<ProjectOut[]>({
    queryKey: ['projects'],
    queryFn: () => listProjects().then(r => r.data),
  })

  const createMut = useMutation({
    mutationFn: (name: string) => createProject(name),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['projects'] }); setCreating(false); setNewName('') },
  })

  const updateMut = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => updateProject(id, { name }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['projects'] }); setEditingId(null) },
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteProject(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['projects'] }),
  })

  return (
    <div className="mx-2 mb-1">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-xs font-medium transition-colors hover:bg-[var(--surface-2)]"
        style={{ color: 'var(--text-2)' }}
      >
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        <Folder size={13} />
        <span className="flex-1 text-left uppercase tracking-wider">Projeler</span>
        <button
          onClick={(e) => { e.stopPropagation(); setCreating(true); setOpen(true) }}
          className="p-0.5 rounded hover:bg-[var(--surface-3)] transition-colors"
          title="Yeni proje"
        >
          <FolderPlus size={13} />
        </button>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            {creating && (
              <div className="flex items-center gap-1 px-2 py-1 mt-0.5">
                <input
                  autoFocus
                  value={newName}
                  onChange={e => setNewName(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === 'Enter' && newName.trim()) createMut.mutate(newName.trim())
                    if (e.key === 'Escape') { setCreating(false); setNewName('') }
                  }}
                  placeholder="Proje adı..."
                  className="flex-1 text-xs px-2 py-1 rounded-lg outline-none"
                  style={{ background: 'var(--surface-2)', color: 'var(--text)', border: '1px solid var(--accent)' }}
                />
                <button onClick={() => newName.trim() && createMut.mutate(newName.trim())}
                  className="p-1 rounded hover:bg-[var(--surface-2)]" style={{ color: 'var(--accent)' }}>
                  <Check size={12} />
                </button>
                <button onClick={() => { setCreating(false); setNewName('') }}
                  className="p-1 rounded hover:bg-[var(--surface-2)]" style={{ color: 'var(--text-3)' }}>
                  <X size={12} />
                </button>
              </div>
            )}

            {projects.length === 0 && !creating && (
              <p className="px-4 py-1 text-xs" style={{ color: 'var(--text-3)' }}>Henüz proje yok</p>
            )}

            {projects.map(p => (
              <div key={p.id}
                className="group flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-xs transition-colors hover:bg-[var(--surface-2)]"
                style={{ color: 'var(--text)' }}
              >
                {editingId === p.id ? (
                  <>
                    <input
                      autoFocus
                      value={editVal}
                      onChange={e => setEditVal(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === 'Enter' && editVal.trim()) updateMut.mutate({ id: p.id, name: editVal.trim() })
                        if (e.key === 'Escape') setEditingId(null)
                      }}
                      className="flex-1 text-xs px-1.5 py-0.5 rounded outline-none"
                      style={{ background: 'var(--surface-2)', color: 'var(--text)', border: '1px solid var(--accent)' }}
                    />
                    <button onClick={() => editVal.trim() && updateMut.mutate({ id: p.id, name: editVal.trim() })}
                      style={{ color: 'var(--accent)' }}><Check size={12} /></button>
                    <button onClick={() => setEditingId(null)}
                      style={{ color: 'var(--text-3)' }}><X size={12} /></button>
                  </>
                ) : (
                  <>
                    <Folder size={12} style={{ color: 'var(--accent)', flexShrink: 0 }} />
                    <span className="flex-1 truncate">{p.name}</span>
                    <span className="text-[10px]" style={{ color: 'var(--text-3)' }}>{p.chat_count}</span>
                    <div className="hidden group-hover:flex items-center gap-0.5">
                      <button onClick={() => { setEditingId(p.id); setEditVal(p.name) }}
                        className="p-0.5 rounded hover:bg-[var(--surface-3)]" style={{ color: 'var(--text-2)' }}>
                        <Pencil size={11} />
                      </button>
                      <button onClick={() => deleteMut.mutate(p.id)}
                        className="p-0.5 rounded hover:bg-[var(--surface-3)]" style={{ color: 'var(--error)' }}>
                        <Trash2 size={11} />
                      </button>
                    </div>
                  </>
                )}
              </div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
