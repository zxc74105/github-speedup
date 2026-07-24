import { useEffect, useState } from 'react'
import { Button, Table, Progress, Tag, Tabs, Descriptions, Modal, Input, InputNumber, message, Space } from 'antd'
import { PlusOutlined, PauseCircleOutlined, CloseCircleOutlined, FolderOpenOutlined, DownloadOutlined } from '@ant-design/icons'
import { useStore } from '../store/useStore'

export default function DownloadPage() {
  const tasks = useStore((s) => s.tasks)
  const addTask = useStore((s) => s.addTask)
  const selectedTaskId = useStore((s) => s.selectedTaskId)
  const setSelectedTaskId = useStore((s) => s.setSelectedTaskId)
  const [modalOpen, setModalOpen] = useState(false)
  const [url, setUrl] = useState('')
  const [saveDir, setSaveDir] = useState('')
  const [concurrency, setConcurrency] = useState(20)
  const [filter, setFilter] = useState('all')

  const filteredTasks = tasks.filter((t) => {
    if (filter === 'all') return true
    if (filter === 'downloading') return t.status === 'downloading' || t.status === 'preparing'
    if (filter === 'completed') return t.status === 'completed'
    if (filter === 'failed') return t.status === 'failed'
    return true
  })

  const selectedTask = tasks.find((t) => t.id === selectedTaskId)

  useEffect(() => {
    const setupEvents = async () => {
      try {
        const wailsRuntime = (window as any).runtime
        if (wailsRuntime?.EventsOn) {
          wailsRuntime.EventsOn('download:progress', (data: any) => {
            // progress updates from backend
          })
        }
      } catch (e) { /* ignore */ }
    }
    setupEvents()
  }, [])

  const handleCreateTask = async () => {
    if (!url) { message.error('请输入下载链接'); return }
    try {
      const api = (window as any).go.bindings.DownloadAPI
      const task = await api.CreateTask({
        url,
        saveDir: saveDir || '',
        concurrency,
        partSize: 10,
        maxRetry: 3,
        timeout: 30,
      })
      addTask(task)
      setModalOpen(false)
      setUrl('')
      message.success('任务已创建')
    } catch (e: any) {
      message.error('创建任务失败: ' + e.message)
    }
  }

  const formatBytes = (bytes: number) => {
    if (bytes < 1024) return bytes + ' B'
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
    return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB'
  }

  const formatSpeed = (speed: number) => {
    if (speed <= 0) return '-'
    const mbps = (speed * 8) / 1000000
    return mbps.toFixed(1) + ' Mbps'
  }

  const statusColor: Record<string, string> = {
    preparing: 'processing',
    downloading: 'processing',
    paused: 'warning',
    completed: 'success',
    failed: 'error',
  }

  const statusText: Record<string, string> = {
    preparing: '准备中',
    downloading: '下载中',
    paused: '已暂停',
    completed: '已完成',
    failed: '失败',
  }

  const columns = [
    {
      title: '文件名',
      dataIndex: 'fileName',
      key: 'fileName',
      render: (_: any, row: any) => (
        <div>
          <div style={{ fontWeight: 500, fontSize: 13 }}>{row.fileName}</div>
          <div style={{ fontSize: 11, color: '#999' }}>📁 {row.saveDir}</div>
        </div>
      ),
    },
    { title: '大小', dataIndex: 'totalBytes', key: 'totalBytes', width: 100, render: (v: number) => formatBytes(v), align: 'right' as const },
    {
      title: '进度', key: 'progress', width: 180,
      render: (_: any, row: any) => (
        <div>
          <Progress percent={Math.round(row.progress || 0)} size="small" style={{ marginBottom: 0 }} />
          <div style={{ fontSize: 11, color: '#888' }}>{formatBytes(row.downloaded)} / {formatBytes(row.totalBytes)}</div>
        </div>
      ),
    },
    { title: '速度', dataIndex: 'speed', key: 'speed', width: 110, render: (v: number) => <span style={{ fontFamily: 'monospace', color: '#155DFC' }}>{formatSpeed(v)}</span>, align: 'right' as const },
    { title: '剩余', dataIndex: 'eta', key: 'eta', width: 80, render: (v: string) => v || '-', align: 'right' as const },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 100,
      render: (v: string) => <Tag color={statusColor[v] || 'default'}>{statusText[v] || v}</Tag>,
    },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ padding: '12px 20px', borderBottom: '1px solid #f0f0f0', display: 'flex', gap: 8, alignItems: 'center', background: '#fafbfc' }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>新建任务</Button>
        <Button icon={<PauseCircleOutlined />}>暂停</Button>
        <Button icon={<CloseCircleOutlined />}>取消</Button>
        <div style={{ flex: 1 }} />
        <Button.Group>
          {['all', 'downloading', 'completed', 'failed'].map((f) => (
            <Button key={f} type={filter === f ? 'primary' : 'default'} size="small" onClick={() => setFilter(f)}>
              {{ all: '全部', downloading: '下载中', completed: '已完成', failed: '失败' }[f]}
            </Button>
          ))}
        </Button.Group>
      </div>

      <Table
        dataSource={filteredTasks}
        columns={columns}
        rowKey="id"
        pagination={false}
        size="small"
        onRow={(record) => ({
          onClick: () => setSelectedTaskId(record.id),
          style: { cursor: 'pointer', background: record.id === selectedTaskId ? '#f0f4ff' : undefined },
        })}
        style={{ flex: 1 }}
        scroll={{ y: 'calc(100vh - 300px)' }}
      />

      {selectedTask && (
        <div style={{ borderTop: '1px solid #e8e8e8', background: '#fafbfc', padding: '12px 20px', flexShrink: 0 }}>
          <Tabs size="small" items={[
            {
              key: 'details', label: '详情',
              children: (
                <Descriptions size="small" column={3}>
                  <Descriptions.Item label="文件名">{selectedTask.fileName}</Descriptions.Item>
                  <Descriptions.Item label="大小">{formatBytes(selectedTask.totalBytes)}</Descriptions.Item>
                  <Descriptions.Item label="下载">{formatBytes(selectedTask.downloaded)}</Descriptions.Item>
                  <Descriptions.Item label="速度">{formatSpeed(selectedTask.speed)}</Descriptions.Item>
                  <Descriptions.Item label="状态"><Tag color={statusColor[selectedTask.status]}>{statusText[selectedTask.status]}</Tag></Descriptions.Item>
                  <Descriptions.Item label="保存文件夹">📁 {selectedTask.saveDir}</Descriptions.Item>
                </Descriptions>
              ),
            },
            { key: 'workers', label: 'Worker', children: <div style={{ color: '#999', fontSize: 12 }}>Worker 实时状态</div> },
            { key: 'speed', label: '速度', children: <div style={{ color: '#999', fontSize: 12 }}>速度趋势图</div> },
            { key: 'log', label: '日志', children: <div style={{ color: '#999', fontSize: 12 }}>事件日志</div> },
          ]} />
        </div>
      )}

      <Modal title="新建下载任务" open={modalOpen} onOk={handleCreateTask} onCancel={() => setModalOpen(false)} okText="开始下载" cancelText="取消">
        <Space direction="vertical" style={{ width: '100%' }}>
          <div>
            <div style={{ marginBottom: 4, fontSize: 12, color: '#666' }}>下载链接</div>
            <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://github.com/..." />
          </div>
          <div>
            <div style={{ marginBottom: 4, fontSize: 12, color: '#666' }}>保存到文件夹</div>
            <Input value={saveDir} onChange={(e) => setSaveDir(e.target.value)} placeholder="D:\Downloads" />
          </div>
          <div style={{ display: 'flex', gap: 12 }}>
            <div><span style={{ fontSize: 12, color: '#666' }}>并发数</span><InputNumber min={1} max={50} value={concurrency} onChange={(v) => setConcurrency(v || 20)} style={{ width: 80, marginLeft: 8 }} /></div>
            <div><span style={{ fontSize: 12, color: '#666' }}>分片</span><InputNumber min={5} max={50} defaultValue={10} style={{ width: 80, marginLeft: 8 }} /></div>
            <div><span style={{ fontSize: 12, color: '#666' }}>重试</span><InputNumber min={0} max={10} defaultValue={3} style={{ width: 80, marginLeft: 8 }} /></div>
          </div>
        </Space>
      </Modal>
    </div>
  )
}
