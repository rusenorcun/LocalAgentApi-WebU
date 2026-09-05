import { api } from './client'

export interface OllamaConnection {
  id: string
  name: string
  base_url: string
  proxy_url: string
  api_key_masked?: string | null
  is_default: boolean
  enabled: boolean
  is_local: boolean
  is_https: boolean
  notes?: string | null
  last_seen_ok?: string | null
  models: string[]
}

export interface OllamaConnectionCreate {
  name: string
  base_url: string
  api_key?: string
  is_default?: boolean
  enabled?: boolean
  notes?: string
}

export interface OllamaConnectionUpdate {
  name?: string
  base_url?: string
  api_key?: string
  is_default?: boolean
  enabled?: boolean
  notes?: string
}

export const listOllamaConnections = () =>
  api.get<OllamaConnection[]>('/api/v2/ollama/connections').then((r) => r.data)

export const getOllamaConnection = (id: string) =>
  api.get<OllamaConnection>(`/api/v2/ollama/connections/${id}`).then((r) => r.data)

export const createOllamaConnection = (body: OllamaConnectionCreate) =>
  api.post<OllamaConnection>('/api/v2/ollama/connections', body).then((r) => r.data)

export const updateOllamaConnection = (id: string, body: OllamaConnectionUpdate) =>
  api.patch<OllamaConnection>(`/api/v2/ollama/connections/${id}`, body).then((r) => r.data)

export const deleteOllamaConnection = (id: string) =>
  api.delete<{ deleted: boolean }>(`/api/v2/ollama/connections/${id}`).then((r) => r.data)

export const testOllamaConnection = (id: string) =>
  api.post<{ ok: boolean; models: string[]; count: number; error?: string }>(
    `/api/v2/ollama/connections/${id}/test`).then((r) => r.data)

export const listConnectionModels = (id: string) =>
  api.get<{ models: string[] }>(`/api/v2/ollama/connections/${id}/models`).then((r) => r.data)
