import { api } from './client'

export interface ChatSummary {
  id: string; title: string; model: string; pinned: boolean
  token_count: number; created_at: string; updated_at: string
}
export interface Source { title?: string; url?: string; snippet?: string }
export interface Message {
  id?: number; role: 'user' | 'assistant' | 'system'; content: string
  tokens: number; model?: string; attachments?: Attachment[]; sources?: Source[]; ts?: string
  thinking?: string | null
  parent_id?: number | null; branch_index?: number; branch_count?: number; siblings?: number[]
}
export interface Attachment { name: string; text?: string; num_images?: number }
export interface Chat extends ChatSummary {
  messages: Message[]; summary: string; summarized_count: number; max_tokens: number; system_prompt?: string
}

export const getChats = () => api.get<{ chats: ChatSummary[] }>('/api/v2/chats')
export const listChats = getChats
export const createChat = (title?: string, model?: string) =>
  api.post<ChatSummary>('/api/v2/chats', { title, model })
export const getChat = (id: string) => api.get<Chat>(`/api/v2/chats/${id}`)
export const patchChat = (id: string, data: Partial<ChatSummary> & { system_prompt?: string }) =>
  api.patch<ChatSummary>(`/api/v2/chats/${id}`, data)
export const deleteChat = (id: string) => api.delete(`/api/v2/chats/${id}`)
export const searchChats = (q: string) =>
  api.get<{ results: Array<{chat_id: string; snippet: string; ts: string}> }>(`/api/v2/chats/search?q=${encodeURIComponent(q)}`)
export const uploadFile = (chatId: string, file: File) => {
  const form = new FormData()
  form.append('file', file)
  return api.post(`/api/v2/chats/${chatId}/upload`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}
export const clearUpload = (chatId: string) =>
  api.delete(`/api/v2/chats/${chatId}/upload`)
export const truncateChat = (chatId: string, messageId: number) =>
  api.post(`/api/v2/chats/${chatId}/truncate`, { message_id: messageId })
export const selectBranch = (chatId: string, messageId: number) =>
  api.post(`/api/v2/chats/${chatId}/select-branch`, { message_id: messageId })

// Devam eden üretimin canlı anlık görüntüsü (yeniden giriş senaryosu)
export interface LiveState {
  active: boolean; finished: boolean; error?: string | null
  elapsed?: number; queued?: number | null
  status?: { status?: string; message?: string } | null
  text?: string; thinking?: string
  tools?: string[]; sources_count?: number
}
export const getChatLive = (id: string) =>
  api.get<LiveState>(`/api/v2/chats/${id}/live`).then((r) => r.data)
