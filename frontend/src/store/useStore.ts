import { create } from 'zustand'

export interface TaskInfo {
  id: number
  url: string
  fileName: string
  saveDir: string
  totalBytes: number
  downloaded: number
  speed: number
  eta: string
  status: string
  progress: number
  createdAt: string
}

export interface ProxyItem {
  domain: string
  enabled: boolean
  status: string
  latency: string
  speed: string
}

export interface ProxyRecord {
  domain: string
  successCount: number
  totalBytes: number
  averageSpeed: number
  failCount: number
  firstUsedAt: string
  lastUsedAt: string
}

export interface Settings {
  defaultSaveDir: string
  defaultConcurrency: number
  partSize: number
  maxRetry: number
  timeout: number
  autoTestOnStart: boolean
  silentSpeedThreshold: number
  silentLatencyThreshold: number
  tcpTimeout: number
  testFileSize: string
  theme: string
  language: string
  checkUpdate: boolean
  enableHTTPAPI: boolean
  httpAPIPort: number
  allowRemoteAccess: boolean
}

interface AppState {
  tasks: TaskInfo[]
  proxies: ProxyItem[]
  records: ProxyRecord[]
  settings: Settings | null
  selectedTaskId: number | null
  activePage: string
  silentCount: number
  setTasks: (tasks: TaskInfo[]) => void
  addTask: (task: TaskInfo) => void
  setProxies: (proxies: ProxyItem[]) => void
  setRecords: (records: ProxyRecord[]) => void
  setSettings: (settings: Settings) => void
  setSelectedTaskId: (id: number | null) => void
  setActivePage: (page: string) => void
  setSilentCount: (n: number) => void
}

export const useStore = create<AppState>((set) => ({
  tasks: [],
  proxies: [],
  records: [],
  settings: null,
  selectedTaskId: null,
  activePage: 'download',
  silentCount: 0,
  setTasks: (tasks) => set({ tasks }),
  addTask: (task) => set((s) => ({ tasks: [...s.tasks, task] })),
  setProxies: (proxies) => set({ proxies }),
  setRecords: (records) => set({ records }),
  setSettings: (settings) => set({ settings }),
  setSelectedTaskId: (id) => set({ selectedTaskId: id }),
  setActivePage: (page) => set({ activePage: page }),
  setSilentCount: (n) => set({ silentCount: n }),
}))
