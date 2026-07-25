import { useEffect, useState } from 'react'
import { Button, Table, Tag, Input, Select, Space, message, Modal, Progress } from 'antd'
import { ReloadOutlined, DeleteOutlined, DownloadOutlined, UploadOutlined, SearchOutlined } from '@ant-design/icons'
import { useStore } from '../store/useStore'

export default function ProxyPage() {
  const proxies = useStore((s) => s.proxies)
  const setProxies = useStore((s) => s.setProxies)
  const records = useStore((s) => s.records)
  const setRecords = useStore((s) => s.setRecords)
  const setSilentCount = useStore((s) => s.setSilentCount)
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('all')
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([])
  const [testing, setTesting] = useState(false)

  const filteredProxies = proxies.filter((p) => {
    if (search && !p.domain.includes(search)) return false
    if (typeFilter !== 'all' && p.type !== typeFilter) return false
    return true
  })

  const handleTestAll = async () => {
    setTesting(true)
    try {
      const api = (window as any).go.bindings.ProxyAPI
      await api.TestAllProxies()
      const updated = await api.GetProxies()
      setProxies(updated)
      message.success('测速完成')
    } catch (e: any) {
      message.error('测速失败: ' + e.message)
    }
    setTesting(false)
  }

  const handlePreflight = async () => {
    try {
      const api = (window as any).go.bindings.ProxyAPI
      const result = await api.PreflightCheck()
      setSilentCount(result.silent)
      const updated = await api.GetProxies()
      setProxies(updated)
      message.success(`预检完成: ${result.available} 可用, ${result.silent} 静默`)
    } catch (e: any) {
      message.error('预检失败: ' + e.message)
    }
  }

  const handleImport = async () => {
    try {
      const api = (window as any).go.bindings.ProxyAPI
      const count = await api.ImportProxies('proxies.json')
      const updated = await api.GetProxies()
      setProxies(updated)
      message.success(`导入 ${count} 个代理`)
    } catch (e: any) {
      message.error('导入失败: ' + e.message)
    }
  }

  const handleDelete = () => {
    if (selectedRowKeys.length === 0) { message.warning('请选择要删除的代理'); return }
    Modal.confirm({
      title: '确定删除选中的代理？',
      content: `将删除 ${selectedRowKeys.length} 个代理及其成功记录`,
      onOk: async () => {
        try {
          const api = (window as any).go.bindings.DownloadAPI
          await api.DeleteProxies(selectedRowKeys)
          message.success('已删除')
          setSelectedRowKeys([])
          const records = await api.GetSuccessRecords()
          setRecords(records)
        } catch (e: any) {
          message.error('删除失败: ' + e.message)
        }
      },
    })
  }

  const proxyColumns = [
    {
      title: '域名', dataIndex: 'domain', key: 'domain',
      render: (_: any, row: any) => (
        <Space>
          <span style={{ width: 7, height: 7, borderRadius: '50%', background: row.status === 'active' ? '#00c853' : row.status === 'silent' ? '#ffb300' : row.status === 'offline' ? '#ff1744' : '#90caf9', display: 'inline-block' }} />
          {row.domain}
        </Space>
      ),
    },
    {
      title: '当前状态', key: 'status', width: 100,
      render: (_: any, row: any) => {
        const colors: Record<string, string> = { active: 'green', silent: 'orange', offline: 'red', checking: 'processing' }
        const texts: Record<string, string> = { active: '可用', silent: '静默', offline: '离线', checking: '检测中' }
        return <Tag color={colors[row.status]}>{texts[row.status] || row.status}</Tag>
      },
    },
    { title: '延迟', dataIndex: 'latency', key: 'latency', width: 90, align: 'right' as const },
    { title: '速度', dataIndex: 'speed', key: 'speed', width: 120, align: 'right' as const },
    { title: '类型', dataIndex: 'type', key: 'type', width: 100, render: (v: string) => <Tag>{v}</Tag> },
  ]

  const recordColumns = [
    { title: '排名', key: 'rank', width: 60, render: (_: any, _r: any, i: number) => <span style={{ fontWeight: 700, color: i < 3 ? '#f9a825' : '#888' }}>#{i + 1}</span> },
    { title: '域名', dataIndex: 'domain', key: 'domain' },
    {
      title: '成功次数', key: 'count', width: 200,
      render: (_: any, row: any) => (
        <Space>
          <Progress percent={Math.min(100, (row.successCount / 50) * 100)} size="small" style={{ width: 80 }} showInfo={false} />
          <span>{row.successCount} 次</span>
        </Space>
      ),
    },
    { title: '总大小', dataIndex: 'totalBytes', key: 'totalBytes', width: 100, render: (v: number) => v ? (v / (1024 * 1024 * 1024)).toFixed(1) + ' GB' : '-' },
    { title: '最近使用', dataIndex: 'lastUsedAt', key: 'lastUsedAt', width: 120, render: (v: string) => v ? new Date(v).toLocaleDateString() : '从未' },
  ]

  return (
    <div style={{ padding: 20 }}>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        <Button type="primary" icon={<ReloadOutlined />} onClick={handleTestAll} loading={testing}>全部测速</Button>
        <Button icon={<ReloadOutlined />} onClick={handlePreflight}>代理预检</Button>
        <Button icon={<UploadOutlined />} onClick={handleImport}>导入</Button>
        <Button icon={<DownloadOutlined />}>导出</Button>
        <Button danger icon={<DeleteOutlined />} onClick={handleDelete}>删除选中</Button>
        <div style={{ flex: 1 }} />
        <Input prefix={<SearchOutlined />} placeholder="搜索域名" value={search} onChange={(e) => setSearch(e.target.value)} style={{ width: 180 }} />
        <Select value={typeFilter} onChange={setTypeFilter} style={{ width: 120 }}>
          <Select.Option value="all">全部类型</Select.Option>
          <Select.Option value="contribute">contribute</Select.Option>
          <Select.Option value="search">search</Select.Option>
          <Select.Option value="user">user</Select.Option>
        </Select>
      </div>

      <Table
        dataSource={filteredProxies}
        columns={proxyColumns}
        rowKey="domain"
        size="small"
        pagination={{ pageSize: 10 }}
        rowSelection={{ selectedRowKeys, onChange: (keys) => setSelectedRowKeys(keys as string[]) }}
        style={{ marginBottom: 24 }}
      />

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <span style={{ fontSize: 13, fontWeight: 600 }}>🏆 成功代理记录</span>
        <span style={{ fontSize: 11, color: '#aaa' }}>按成功下载次数排序，使用越多越靠前</span>
      </div>

      <Table
        dataSource={records}
        columns={recordColumns}
        rowKey="domain"
        size="small"
        pagination={false}
      />
    </div>
  )
}
