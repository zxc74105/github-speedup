import { useEffect } from 'react'
import { App as AntApp, ConfigProvider, Layout, Menu } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { DownloadOutlined, GlobalOutlined, SettingOutlined, InboxOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons'
import { useStore } from './store/useStore'
import DownloadPage from './pages/DownloadPage'
import ProxyPage from './pages/ProxyPage'
import SettingsPage from './pages/SettingsPage'
import './App.css'

const { Sider, Content } = Layout

function App() {
  const activePage = useStore((s) => s.activePage)
  const setActivePage = useStore((s) => s.setActivePage)
  const silentCount = useStore((s) => s.silentCount)
  const loadProxies = async () => {
    try {
      const bindings = (window as any).go?.bindings
      if (!bindings?.ProxyAPI) return
      const proxies = await bindings.ProxyAPI.GetProxies()
      useStore.getState().setProxies(proxies)
    } catch (e) { console.error(e) }
  }
  const loadRecords = async () => {
    try {
      const bindings = (window as any).go?.bindings
      if (!bindings?.DownloadAPI) return
      const records = await bindings.DownloadAPI.GetSuccessRecords()
      useStore.getState().setRecords(records)
    } catch (e) { console.error(e) }
  }

  useEffect(() => {
    loadProxies()
    loadRecords()
  }, [])

  const menuItems = [
    { key: 'download', icon: <DownloadOutlined />, label: '下载管理' },
    { key: 'proxies', icon: <GlobalOutlined />, label: '代理管理' },
    { key: 'settings', icon: <SettingOutlined />, label: '设置' },
  ]

  const renderPage = () => {
    switch (activePage) {
      case 'download': return <DownloadPage />
      case 'proxies': return <ProxyPage />
      case 'settings': return <SettingsPage />
      default: return <DownloadPage />
    }
  }

  return (
    <ConfigProvider locale={zhCN} theme={{
      token: {
        colorPrimary: '#155DFC',
        borderRadius: 6,
      },
    }}>
      <AntApp><Layout style={{ height: '100vh', background: '#f5f6f8' }}>
        <Sider width={180} theme="light" style={{ borderRight: '1px solid #e0e0e0', background: '#f5f6f8' }}>
          <div style={{ padding: '14px 16px', fontWeight: 700, fontSize: 14, color: '#1a1a2e', borderBottom: '1px solid #e8e8e8', display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ width: 16, height: 16, background: 'linear-gradient(135deg,#155DFC,#764ba2)', borderRadius: 4, display: 'inline-block' }} />
            Multi-Proxy DL
          </div>
          <Menu
            mode="inline"
            selectedKeys={[activePage]}
            onClick={({ key }) => setActivePage(key)}
            items={menuItems}
            style={{ background: 'transparent', borderRight: 0, marginTop: 8 }}
          />
          {silentCount > 0 && (
            <div style={{ padding: '8px 16px', fontSize: 11, color: '#e53935' }}>
              静默: {silentCount} 个代理
            </div>
          )}
        </Sider>
        <Content style={{ overflow: 'auto', background: '#fff' }}>
          {renderPage()}
        </Content>
      </Layout></AntApp>
    </ConfigProvider>
  )
}

export default App
