import { api } from './client'

// Sistem izleci metrikleri — GET /api/v2/system/stats (giriş yapmış kullanıcı)
export interface SystemStats {
  cpu_usage: number
  memory_usage: number
  disk_usage: number
  active_processes: number
  running_model: string | null
  cpu_count?: number | null
  memory_used_gb?: number | null
  memory_total_gb?: number | null
  disk_used_gb?: number | null
  disk_total_gb?: number | null
  uptime_seconds?: number | null
  load_avg?: number[] | null
  platform?: string | null
}

export const fetchSystemStats = () =>
  api.get<SystemStats>('/api/v2/system/stats').then((r) => r.data)
