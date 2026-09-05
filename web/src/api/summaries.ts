import { api } from './client'

export interface SummaryOut {
  id: string;
  title: string;
  summary_text: string;
  source_chat_ids: string;
  created_at: string;
}

export const batchSummarize = (chatIds: string[]) =>
  api.post<{ id: string; title: string; summary_text: string; source_chat_ids: string; created_at: string }>(
    '/api/v2/chats/batch-summarize',
    { chat_ids: chatIds }
  )

export const listSummaries = () =>
  api.get<SummaryOut[]>('/api/v2/summaries')

export const deleteSummary = (id: string) =>
  api.delete(`/api/v2/summaries/${id}`)

export const injectSummary = (chatId: string, summaryId: string) =>
  api.post<{ name: string; num_images: number }>(`/api/v2/chats/${chatId}/inject-summary`, { summary_id: summaryId })
