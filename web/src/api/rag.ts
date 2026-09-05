import { api } from './client'

export const listDocuments = () => api.get('/api/v2/rag/documents')
export const deleteDocument = (id: number) => api.delete(`/api/v2/rag/documents/${id}`)
export const queryRag = (q: string, docIds?: number[]) =>
  api.post<{ chunks: Array<{ text: string; doc_name: string; score: number }> }>(
    '/api/v2/rag/query', { q, doc_ids: docIds }
  )
export const uploadDocument = (file: File) => {
  const form = new FormData()
  form.append('file', file)
  return api.post('/api/v2/rag/documents', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}
export const injectDocument = (chatId: string, documentId: number) =>
  api.post(`/api/v2/chats/${chatId}/inject-document`, { document_id: documentId })
