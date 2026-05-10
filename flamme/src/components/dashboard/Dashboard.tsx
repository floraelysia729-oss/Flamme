import { useEffect, useState } from 'react'
import { api } from '../../lib/api'

export default function Dashboard() {
  const [stats, setStats] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.status()
      .then(data => setStats(data))
      .catch(() => setStats(null))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div style={{ padding: 32, maxWidth: 1200, margin: '0 auto' }}>
      <h1 style={{ fontSize: 24, fontWeight: 600, marginBottom: 8, color: 'var(--text-100)' }}>
        欢迎回来
      </h1>
      <p style={{ color: 'var(--text-200)', marginBottom: 32 }}>
        {loading ? '加载中...' :
          stats ?
            `知识库有 ${stats.total_documents} 个文档，${stats.total_tags} 个标签` :
            '知识库未连接'
        }
      </p>

      {/* 卡片区域 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 24 }}>
        <StatCard title="文档总数" value={stats?.total_documents ?? '-'} />
        <StatCard title="向量索引" value={stats ? `${stats.embedded}/${stats.total_documents}` : '-'} />
        <StatCard title="标签数" value={stats?.total_tags ?? '-'} />
      </div>

      {/* 知识图谱缩略区 */}
      <div style={{
        background: '#fff',
        borderRadius: 12,
        padding: 24,
        border: '1px solid var(--bg-300)',
        textAlign: 'center',
        color: 'var(--text-200)',
      }}>
        <p>知识图谱交互视图</p>
        <p style={{ fontSize: 13 }}>点击侧边栏 🔗 进入全屏图谱</p>
      </div>
    </div>
  )
}

function StatCard({ title, value }: { title: string; value: string | number }) {
  return (
    <div style={{
      background: '#fff',
      borderRadius: 12,
      padding: 20,
      border: '1px solid var(--bg-300)',
    }}>
      <div style={{ fontSize: 13, color: 'var(--text-200)', marginBottom: 8 }}>{title}</div>
      <div style={{ fontSize: 28, fontWeight: 600, color: 'var(--primary-100)' }}>{value}</div>
    </div>
  )
}
