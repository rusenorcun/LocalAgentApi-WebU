import { api } from './client'

export interface ProjectOut {
  id: string
  name: string
  description: string | null
  chat_count: number
  doc_count: number
  created_at: string
  updated_at: string
}

export interface DocOut {
  id: number
  name: string
  status: string
  created_at: string
}

export const listProjects = () =>
  api.get<ProjectOut[]>('/api/v2/projects')

export const createProject = (name: string, description?: string) =>
  api.post<ProjectOut>('/api/v2/projects', { name, description })

export const updateProject = (id: string, data: { name?: string; description?: string }) =>
  api.patch<ProjectOut>(`/api/v2/projects/${id}`, data)

export const deleteProject = (id: string) =>
  api.delete(`/api/v2/projects/${id}`)

export const addChatToProject = (projectId: string, chatId: string) =>
  api.post(`/api/v2/projects/${projectId}/chats`, { chat_id: chatId })

export const removeChatFromProject = (projectId: string, chatId: string) =>
  api.delete(`/api/v2/projects/${projectId}/chats/${chatId}`)

export const listProjectDocs = (projectId: string) =>
  api.get<DocOut[]>(`/api/v2/projects/${projectId}/documents`)

export const addDocToProject = (projectId: string, docId: number) =>
  api.post(`/api/v2/projects/${projectId}/documents`, { doc_id: docId })

export const removeDocFromProject = (projectId: string, docId: number) =>
  api.delete(`/api/v2/projects/${projectId}/documents/${docId}`)
