import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

export interface SearchConfig {
  id: number
  name: string
  query: string
  search_type: string
  sort_type: number
  publish_time: number
  content_type: number
  filter_duration: string
  limit: number
  enabled: boolean
  cron: string
  feishu_webhook: string
  channel_id: number | null
  llm_filter_enabled: boolean
  created_at: string
}

export interface TaskRecord {
  id: number
  config_id: number
  status: string
  total: number
  downloaded: number
  sent: number
  error: string | null
  created_at: string
}

export interface AppSetting {
  id: number
  key: string
  value: string
}

export interface CookieAccount {
  id: number
  name: string
  cookie: string
  note: string
  is_default: boolean
  created_at: string
}

export interface NotifyChannel {
  id: number
  name: string
  channel_type: string
  app_id: string
  app_secret: string
  chat_id: string
  webhook_url: string   // 保留兼容
  is_default: boolean
  created_at: string
}

export interface LogEntry {
  ts: string
  task_id: number
  config_name: string
  aweme_id: string
  media_type: string
  author: string
  desc: string
  video_url: string | null
  image_urls: string[]
  downloaded: boolean
  file_paths: string[]
  sent: boolean
  error: string | null
}

export const configsApi = {
  list: () => api.get<SearchConfig[]>('/configs').then(r => r.data),
  create: (data: Omit<SearchConfig, 'id' | 'created_at'>) =>
    api.post<SearchConfig>('/configs', data).then(r => r.data),
  update: (id: number, data: Partial<SearchConfig>) =>
    api.put<SearchConfig>(`/configs/${id}`, data).then(r => r.data),
  delete: (id: number) => api.delete(`/configs/${id}`).then(r => r.data),
  trigger: (id: number) => api.post(`/tasks/trigger/${id}`).then(r => r.data),
}

export const tasksApi = {
  list: () => api.get<TaskRecord[]>('/tasks').then(r => r.data),
  delete: (id: number) => api.delete(`/tasks/${id}`).then(r => r.data),
  clear: () => api.delete('/tasks').then(r => r.data),
}

export const settingsApi = {
  list: () => api.get<AppSetting[]>('/settings').then(r => r.data),
  update: (key: string, value: string) =>
    api.put(`/settings/${key}`, { value }).then(r => r.data),
}

export const cookiesApi = {
  list: () => api.get<CookieAccount[]>('/cookies').then(r => r.data),
  create: (data: Omit<CookieAccount, 'id' | 'created_at'>) =>
    api.post<CookieAccount>('/cookies', data).then(r => r.data),
  update: (id: number, data: Partial<CookieAccount>) =>
    api.put<CookieAccount>(`/cookies/${id}`, data).then(r => r.data),
  delete: (id: number) => api.delete(`/cookies/${id}`).then(r => r.data),
  setDefault: (id: number) => api.post<CookieAccount>(`/cookies/${id}/set-default`).then(r => r.data),
}

export const channelsApi = {
  list: () => api.get<NotifyChannel[]>('/channels').then(r => r.data),
  create: (data: Omit<NotifyChannel, 'id' | 'created_at'>) =>
    api.post<NotifyChannel>('/channels', data).then(r => r.data),
  update: (id: number, data: Partial<NotifyChannel>) =>
    api.put<NotifyChannel>(`/channels/${id}`, data).then(r => r.data),
  delete: (id: number) => api.delete(`/channels/${id}`).then(r => r.data),
  setDefault: (id: number) => api.post<NotifyChannel>(`/channels/${id}/set-default`).then(r => r.data),
  test: (id: number) => api.post<{ ok: boolean; error?: string }>(`/channels/${id}/test`).then(r => r.data),
  listChats: (id: number) => api.get<Array<{ chat_id: string; name: string; avatar: string; description: string }>>(`/channels/${id}/chats`).then(r => r.data),
}

export const logsApi = {
  dates: () => api.get<string[]>('/logs/dates').then(r => r.data),
  entries: (date: string) => api.get<LogEntry[]>(`/logs?date=${date}`).then(r => r.data),
  deleteDate: (date: string) => api.delete(`/logs?date=${date}`).then(r => r.data),
  clearAll: () => api.delete('/logs/all').then(r => r.data),
}

export interface LLMConfig {
  id: number
  name: string
  base_url: string
  api_key: string
  model: string
  prompt_template: string
  is_default: boolean
  created_at: string
}

export const llmApi = {
  list: () => api.get<LLMConfig[]>('/llm').then(r => r.data),
  create: (data: Omit<LLMConfig, 'id' | 'created_at'>) =>
    api.post<LLMConfig>('/llm', data).then(r => r.data),
  update: (id: number, data: Partial<LLMConfig>) =>
    api.put<LLMConfig>(`/llm/${id}`, data).then(r => r.data),
  delete: (id: number) => api.delete(`/llm/${id}`).then(r => r.data),
  setDefault: (id: number) =>
    api.post<LLMConfig>(`/llm/${id}/set-default`).then(r => r.data),
  test: (id: number) =>
    api.post<{ ok: boolean; response?: string; error?: string }>(
      `/llm/${id}/test`
    ).then(r => r.data),
}
