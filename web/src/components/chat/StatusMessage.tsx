import { motion } from 'framer-motion'
import { Upload, Loader2, Search, Sparkles, CheckCircle2, AlertCircle } from 'lucide-react'
import { useEffect, useState } from 'react'

export type StatusType = 'thinking' | 'uploading' | 'processing' | 'searching' | 'summarizing' | 'success' | 'error'

export interface StatusMessageProps {
  type: StatusType
  message: string
  progress?: number // 0-100 for uploading
  subtext?: string
}

const config = {
  thinking: { color: '#8b5cf6', bgColor: 'rgba(139,92,246,0.05)' },
  uploading: { color: '#3b82f6', bgColor: 'rgba(59,130,246,0.05)' },
  processing: { color: '#3b82f6', bgColor: 'rgba(59,130,246,0.05)' },
  searching: { color: '#f59e0b', bgColor: 'rgba(245,158,11,0.05)' },
  summarizing: { color: '#10b981', bgColor: 'rgba(16,185,129,0.05)' },
  success: { color: '#10b981', bgColor: 'rgba(16,185,129,0.05)' },
  error: { color: '#ef4444', bgColor: 'rgba(239,68,68,0.05)' },
}

export default function StatusMessage({ type, message, progress, subtext }: StatusMessageProps) {
  const c = config[type] || config.thinking
  const [show, setShow] = useState(true)

  // Success messages disappear after 3 seconds
  useEffect(() => {
    if (type === 'success') {
      const t = setTimeout(() => setShow(false), 3000)
      return () => clearTimeout(t)
    }
    setShow(true)
  }, [type])

  if (!show) return null

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      className="flex gap-3 max-w-3xl mx-auto w-full my-2"
    >
      {/* Align with messages avatar spacing */}
      <div className="shrink-0 w-7" />
      
      <div 
        className="flex items-center gap-3 px-3 py-2 rounded-lg relative overflow-hidden"
        style={{ 
          background: c.bgColor,
          borderLeft: `3px solid ${c.color}`,
          maxWidth: '60%'
        }}
      >
        {/* Progress bar background for uploading */}
        {type === 'uploading' && progress !== undefined && (
          <div 
            className="absolute left-0 bottom-0 top-0 opacity-10 transition-all duration-300 ease-out"
            style={{ background: c.color, width: `${progress}%` }} 
          />
        )}

        {/* Icon */}
        <div className="shrink-0 flex items-center justify-center relative z-10" style={{ color: c.color }}>
          {type === 'thinking' && (
            <div className="flex gap-1 h-4 items-center px-1">
              {[0,1,2].map((i) => (
                <motion.span key={i} animate={{ y: [0, -4, 0] }}
                  transition={{ duration: 0.6, delay: i*0.15, repeat: Infinity }}
                  className="w-1.5 h-1.5 rounded-full inline-block"
                  style={{ background: c.color }} />
              ))}
            </div>
          )}
          {type === 'uploading' && (
            <motion.div animate={{ y: [-2, 0, -2] }} transition={{ duration: 1, repeat: Infinity }}>
              <Upload size={16} />
            </motion.div>
          )}
          {type === 'processing' && (
            <motion.div animate={{ rotate: 360 }} transition={{ duration: 1, repeat: Infinity, ease: "linear" }}>
              <Loader2 size={16} />
            </motion.div>
          )}
          {type === 'searching' && (
            <motion.div animate={{ rotate: [-5, 5, -5] }} transition={{ duration: 0.8, repeat: Infinity }}>
              <Search size={16} />
            </motion.div>
          )}
          {type === 'summarizing' && (
            <motion.div animate={{ rotate: 360 }} transition={{ duration: 2, repeat: Infinity, ease: "linear" }}>
              <Sparkles size={16} />
            </motion.div>
          )}
          {type === 'success' && (
            <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: "spring", stiffness: 300, damping: 20 }}>
              <CheckCircle2 size={16} />
            </motion.div>
          )}
          {type === 'error' && <AlertCircle size={16} />}
        </div>

        {/* Text content */}
        <div className="flex flex-col relative z-10 min-w-0">
          <span 
            className={`text-[13px] font-medium truncate ${type === 'thinking' ? 'italic' : ''}`}
            style={{ color: c.color }}
          >
            {message}
          </span>
          {subtext && (
            <span className="text-[11px] truncate opacity-70" style={{ color: c.color }}>
              {subtext}
            </span>
          )}
        </div>
      </div>
    </motion.div>
  )
}
