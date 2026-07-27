import { useEffect, useState } from 'react'
import { App, Button, Card, Form, Input, InputNumber, Select, Switch, Radio, Space, Modal, Tag } from 'antd'
import { useStore, Settings } from '../store/useStore'

export default function SettingsPage() {
  const { message } = App.useApp()
  const settings = useStore((s) => s.settings)
  const setSettings = useStore((s) => s.setSettings)
  const setRecords = useStore((s) => s.setRecords)
  const [form] = Form.useForm()
  const [serverRunning, setServerRunning] = useState(false)
  const [serverAddr, setServerAddr] = useState('')

  const getAPI = (name: string) => {
    const b = (window as any).go?.bindings
    return b?.[name]
  }

  const refreshServerStatus = async () => {
    try {
      const api = getAPI('ServerAPI')
      if (!api) return
      const running = await api.IsRunning()
      setServerRunning(running)
      if (running) {
        const addr = await api.GetAddress()
        setServerAddr(addr)
      }
    } catch (e) { /* ignore */ }
  }

  useEffect(() => {
    const load = async () => {
      try {
        const api = getAPI('ConfigAPI')
        if (!api) return
        const s = await api.GetSettings()
        setSettings(s)
        form.setFieldsValue(s)
        refreshServerStatus()
      } catch (e) { console.error(e) }
    }
    load()
  }, [])

  const handleSave = async () => {
    try {
      const values = form.getFieldsValue()
      const api = getAPI('ConfigAPI')
      const serverAPI = getAPI('ServerAPI')
      if (!api || !serverAPI) return

      const wasRunning = await serverAPI.IsRunning()
      if (wasRunning && values.httpAPIPort !== settings?.httpAPIPort) {
        await serverAPI.Stop()
        await serverAPI.Start(values.httpAPIPort, true)
      } else if (!wasRunning) {
        await serverAPI.Start(values.httpAPIPort, true)
      }

      await api.SaveSettings(values)
      setSettings(values)
      refreshServerStatus()
      message.success('设置已保存')
    } catch (e: any) {
      message.error('保存失败: ' + e.message)
    }
  }

  const handleReset = () => {
    Modal.confirm({
      title: '恢复默认设置？',
      onOk: async () => {
        const api = getAPI('ConfigAPI')
        if (!api) return
        const def = await api.ResetSettings()
        setSettings(def)
        form.setFieldsValue(def)
        message.success('已恢复默认')
      },
    })
  }

  const handleClearRecords = () => {
    Modal.confirm({
      title: '清除所有成功代理记录？',
      content: '此操作不可恢复',
      okText: '确认清除',
      okType: 'danger',
      onOk: async () => {
        const api = getAPI('ConfigAPI')
        if (!api) return
        await api.ClearRecords()
        setRecords([])
        message.success('已清除记录')
      },
    })
  }

  const handleExport = async () => {
    try {
      const api = getAPI('ConfigAPI')
      if (!api) return
      const path = await api.ExportRecords()
      message.success('已导出到: ' + path)
    } catch (e: any) {
      message.error('导出失败: ' + e.message)
    }
  }

  return (
    <div style={{ padding: 24, maxWidth: 640, margin: '0 auto' }}>
      <h3 style={{ marginBottom: 20 }}>⚙️ 设置</h3>

      <Form form={form} layout="vertical" initialValues={settings || {}}>
        <Card title="⬇️ 下载设置" style={{ marginBottom: 16 }}>
          <div style={{ marginBottom: 24 }}>
            <div style={{ marginBottom: 4, fontSize: 13, color: '#333' }}>默认下载文件夹</div>
            <div style={{ display: 'flex', gap: 4 }}>
              <Form.Item name="defaultSaveDir" style={{ marginBottom: 0, flex: 1 }}>
                <Input placeholder="D:\Downloads" />
              </Form.Item>
              <Button onClick={async () => {
                try {
                  const api = getAPI('ConfigAPI')
                  if (!api) return
                  const dir = await api.PickDirectory()
                  if (dir) form.setFieldsValue({ defaultSaveDir: dir })
                } catch (e) { console.error('浏览目录失败:', e); message.warning('请手动输入路径') }
              }}>浏览</Button>
            </div>
          </div>
          <Form.Item name="defaultConcurrency" label="默认并发数">
            <InputNumber min={1} max={50} style={{ width: 120 }} />
          </Form.Item>
          <Form.Item name="partSize" label="分片大小 (MB)">
            <Select>
              <Select.Option value={5}>5 MB</Select.Option>
              <Select.Option value={10}>10 MB</Select.Option>
              <Select.Option value={20}>20 MB</Select.Option>
              <Select.Option value={50}>50 MB</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="maxRetry" label="最大重试次数">
            <Select>
              {[0, 1, 2, 3, 5, 10].map((n) => (
                <Select.Option key={n} value={n}>{n === 0 ? '不重试' : n + ' 次'}</Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="timeout" label="请求超时 (秒)">
            <Select>
              {[10, 20, 30, 60, 120].map((n) => (
                <Select.Option key={n} value={n}>{n} 秒</Select.Option>
              ))}
            </Select>
          </Form.Item>
        </Card>

        <Card title="🌐 代理设置" style={{ marginBottom: 16 }}>
          <Form.Item name="autoTestOnStart" label="启动时自动测速" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="silentSpeedThreshold" label="静默速度阈值 (Mbps)">
            <InputNumber min={0.5} max={50} step={0.5} style={{ width: 120 }} />
          </Form.Item>
          <Form.Item name="silentLatencyThreshold" label="静默延迟阈值 (ms)">
            <InputNumber min={100} max={2000} step={50} style={{ width: 120 }} />
          </Form.Item>
          <Form.Item name="tcpTimeout" label="TCP 连接超时 (秒)">
            <Select>
              {[1, 3, 5, 10, 30].map((n) => (
                <Select.Option key={n} value={n}>{n} 秒</Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="testFileSize" label="测速测试文件大小">
            <Select>
              <Select.Option value="512 KB">512 KB</Select.Option>
              <Select.Option value="1 MB">1 MB</Select.Option>
              <Select.Option value="5 MB">5 MB</Select.Option>
            </Select>
          </Form.Item>
        </Card>

        <Card title="🎨 外观" style={{ marginBottom: 16 }}>
          <Form.Item name="theme" label="主题">
            <Radio.Group>
              <Radio value="light">🌞 浅色</Radio>
              <Radio value="dark">🌙 深色</Radio>
              <Radio value="system">💻 跟随系统</Radio>
            </Radio.Group>
          </Form.Item>
          <Form.Item name="language" label="语言">
            <Select style={{ width: 160 }}>
              <Select.Option value="zh-CN">简体中文</Select.Option>
              <Select.Option value="en">English</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="checkUpdate" label="启动时检查更新" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Card>

        <Card title="🔌 HTTP API 加速服务" style={{ marginBottom: 16 }}>
          <div style={{ marginBottom: 12, padding: '6px 10px', background: '#e8f5e9', borderRadius: 4, fontSize: 12, color: '#2e7d32' }}>
            ⚡ 此功能永久开启，无需配置
          </div>
          <Form.Item name="httpAPIPort" label="监听端口">
            <InputNumber min={1024} max={65535} style={{ width: 120 }} disabled />
          </Form.Item>
          <Form.Item name="allowRemoteAccess" label="允许远程访问" valuePropName="checked">
            <Switch checked disabled />
          </Form.Item>
          <div style={{ padding: '8px 12px', background: '#f5f5f5', borderRadius: 6, fontSize: 12, color: '#666' }}>
            <div style={{ marginBottom: 4 }}>
              状态: {serverRunning ? <Tag color="green">● 运行中</Tag> : <Tag>停止</Tag>}
              {serverRunning && <span style={{ marginLeft: 8 }}>地址: <code>{serverAddr}</code></span>}
            </div>
            <div>用法: <code>http://127.0.0.1:{form.getFieldValue('httpAPIPort') || 9090}/https://github.com/.../file.zip</code></div>
          </div>
        </Card>

        <Card title="🗄️ 数据管理" style={{ marginBottom: 16 }}>
          <Space>
            <Button onClick={handleExport}>📤 导出记录</Button>
            <Button danger onClick={handleClearRecords}>🗑 清除所有记录</Button>
            <Button danger onClick={handleReset}>⟲ 重置所有设置</Button>
          </Space>
        </Card>
      </Form>

      <div style={{ textAlign: 'right', marginTop: 16 }}>
        <Space>
          <Button onClick={handleReset}>恢复默认</Button>
          <Button type="primary" onClick={handleSave}>💾 保存设置</Button>
        </Space>
      </div>
    </div>
  )
}
