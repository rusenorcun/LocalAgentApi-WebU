import { api } from './client'

export interface ApiKey {
  id: number
  name: string
  scopes: string
  revoked: boolean
  created_at: string
  last_used_at?: string | null
  masked_key?: string | null
  key?: string // yalnizca olusturma aninda
}

export const listApiKeys = () =>
  api.get<ApiKey[]>('/api/v2/keys').then((r) => r.data)

export const createApiKey = (body: { name: string; scopes?: string }) =>
  api.post<ApiKey>('/api/v2/keys', body).then((r) => r.data)

export const updateApiKey = (id: number, body: Partial<{ name: string; scopes: string; revoked: boolean }>) =>
  api.patch<ApiKey>(`/api/v2/keys/${id}`, body).then((r) => r.data)

export const deleteApiKey = (id: number) =>
  api.delete<{ deleted: boolean }>(`/api/v2/keys/${id}`).then((r) => r.data)
