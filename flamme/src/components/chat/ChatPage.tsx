import { useState, useRef, useEffect, useLayoutEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeRaw from 'rehype-raw'
import rehypeKatex from 'rehype-katex'
import { streamChat } from '../../lib/api'
import { useSession } from '../layout/PageLayout'

interface Message {
  role: 'user' | 'assistant'
  content: string
  toolCalls?: string[]
  duration?: number
  tokenCount?: number
  suggestedQuestions?: string[]
}

/** 格式化秒数为 分:秒 或 秒 */
function formatElapsed(ms: number): string {
  const sec = Math.floor(ms / 1000)
  if (sec < 60) return `${sec}s`
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${m}m${s < 10 ? '0' : ''}${s}s`
}

export default function ChatPage() {
  const { sessionId, setSessionId } = useSession()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [mode, setMode] = useState<'search' | 'learn'>('search')
  const [elapsed, setElapsed] = useState<number>(0)       // 心跳计时 (ms)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const startTimeRef = useRef<number>(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined)
  const scrollToBottomOnNextRender = useRef(false)
  const streamAssistantIndex = useRef<number | null>(null)
  const followAssistantUntilFull = useRef(false)
  const messagesRef = useRef<Message[]>(messages)
  messagesRef.current = messages

  function scrollToBottom() {
    const el = scrollContainerRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }

  function followAssistantReplyUntilFull() {
    const el = scrollContainerRef.current
    const idx = streamAssistantIndex.current
    if (!el || idx === null || !followAssistantUntilFull.current) return

    const assistantEl = el.querySelector<HTMLDivElement>(`[data-message-index="${idx}"]`)
    if (!assistantEl) return

    if (assistantEl.offsetHeight < el.clientHeight) {
      scrollToBottom()
      return
    }

    followAssistantUntilFull.current = false
    el.scrollTop = Math.min(assistantEl.offsetTop, el.scrollHeight - el.clientHeight)
  }

  useLayoutEffect(() => {
    if (scrollToBottomOnNextRender.current) {
      scrollToBottomOnNextRender.current = false
      scrollToBottom()
      return
    }

    followAssistantReplyUntilFull()
  }, [messages])

  // 加载会话历史
  useEffect(() => {
    if (!sessionId) return
    setMessages([])
    import('../../lib/api').then(({ api }) => {
      api.chat.session(sessionId)
        .then((data: any) => {
          if (data.messages && data.messages.length > 0) {
            const msgs: Message[] = []
            for (const m of data.messages) {
              if (m.role === 'user') {
                msgs.push({ role: 'user', content: m.content })
              } else if (m.role === 'assistant') {
                msgs.push({ role: 'assistant', content: m.content })
              }
            }
            scrollToBottomOnNextRender.current = true
            setMessages(msgs)
          }
        })
        .catch(() => {})
    })
  }, [sessionId])

  // 流式结束后清理计时器
  useEffect(() => {
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [])

  function cancelStream() {
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
  }

  async function handleSend(overrideText?: string) {
    const text = (overrideText ?? input).trim()
    if (!text) return

    cancelStream()

    setInput('')
    setStreaming(true)
    setElapsed(0)
    startTimeRef.current = Date.now()

    // 启动心跳计时器
    timerRef.current = setInterval(() => {
      setElapsed(Date.now() - startTimeRef.current)
    }, 1000)

    const idx = messages.length
    streamAssistantIndex.current = idx + 1
    followAssistantUntilFull.current = true
    scrollToBottomOnNextRender.current = true
    setMessages(prev => [...prev, { role: 'user', content: text }, { role: 'assistant', content: '' }])

    const controller = new AbortController()
    abortRef.current = controller

    try {
      let fullContent = ''
      let tokens = 0
      for await (const event of streamChat(text, sessionId, controller.signal, mode)) {
        if (abortRef.current !== controller) return

        if (event.type === 'heartbeat') {
          // 心跳事件 — 只更新计时（timer 已在跑）
          continue
        } else if (event.type === 'token' && event.content) {
          fullContent += event.content
          tokens++
          const current = fullContent
          const tc = tokens
          const dur = Math.round((Date.now() - startTimeRef.current) / 100) / 10
          setMessages(prev => {
            const next = [...prev]
            next[idx + 1] = { ...next[idx + 1], content: current, tokenCount: tc, duration: dur }
            return next
          })
        } else if (event.type === 'tool_call' && event.content) {
          const tc = event.content
          setMessages(prev => {
            const next = [...prev]
            const msg = next[idx + 1]
            next[idx + 1] = {
              ...msg,
              toolCalls: [...(msg.toolCalls || []), tc],
            }
            return next
          })
        } else if (event.type === 'error' && event.content) {
          const errMsg = event.content
          setMessages(prev => {
            const next = [...prev]
            next[idx + 1] = {
              ...next[idx + 1],
              content: next[idx + 1].content + `\n\n**错误:** ${errMsg}`,
            }
            return next
          })
        } else if (event.type === 'suggested_questions' && event.questions) {
          const sq = event.questions
          setMessages(prev => {
            const next = [...prev]
            next[idx + 1] = { ...next[idx + 1], suggestedQuestions: sq }
            return next
          })
        }
      }
      // 完成 — 解析追问建议 + 记录最终耗时
      const finalDur = Math.round((Date.now() - startTimeRef.current) / 100) / 10
      const suggestionsMatch = fullContent.match(/__SUGGESTIONS__\s*:\s*(\[[\s\S]*?\])/)
      let extractedQuestions: string[] | undefined
      let cleanContent = fullContent
      if (suggestionsMatch) {
        try {
          const parsed = JSON.parse(suggestionsMatch[1])
          if (Array.isArray(parsed) && parsed.length > 0) {
            extractedQuestions = parsed
            cleanContent = fullContent.replace(/__SUGGESTIONS__\s*:\s*\[[\s\S]*?\]/, '').trim()
          }
        } catch { /* skip malformed */ }
      }
      const eq = extractedQuestions
      const cc = cleanContent
      setMessages(prev => {
        const next = [...prev]
        next[idx + 1] = {
          ...next[idx + 1],
          duration: finalDur,
          content: cc,
          ...(eq ? { suggestedQuestions: eq } : {}),
        }
        return next
      })
    } catch (e: any) {
      if (abortRef.current !== controller) return

      if (e.name === 'AbortError') {
        setMessages(prev => {
          const next = [...prev]
          next[idx + 1] = { ...next[idx + 1], content: next[idx + 1].content + '\n\n[已取消]' }
          return next
        })
      } else {
        setMessages(prev => {
          const next = [...prev]
          next[idx + 1] = { role: 'assistant', content: `**错误:** ${e.message}` }
          return next
        })
      }
    } finally {
      if (abortRef.current === controller) {
        setStreaming(false)
        setElapsed(0)
        if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = undefined }
        streamAssistantIndex.current = null
        followAssistantUntilFull.current = false
        abortRef.current = null
      }
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0, overflow: 'hidden' }}>
      {/* 标题栏 */}
      <div style={{ padding: '12px 24px', borderBottom: '1px solid var(--bg-300)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0 }}>
        <span style={{ fontWeight: 600 }}>Chat</span>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <div style={{ display: 'flex', borderRadius: 6, overflow: 'hidden', border: '1px solid var(--bg-300)' }}>
            <button
              onClick={() => setMode('search')}
              style={{
                padding: '4px 12px', fontSize: 12, border: 'none', cursor: 'pointer',
                background: mode === 'search' ? 'var(--primary-100)' : '#fff',
                color: mode === 'search' ? '#fff' : 'var(--text-200)',
              }}
            >
              搜索
            </button>
            <button
              onClick={() => setMode('learn')}
              style={{
                padding: '4px 12px', fontSize: 12, border: 'none', cursor: 'pointer',
                background: mode === 'learn' ? 'var(--primary-100)' : '#fff',
                color: mode === 'learn' ? '#fff' : 'var(--text-200)',
              }}
            >
              学习
            </button>
          </div>
          <button
            onClick={() => setSessionId(crypto.randomUUID())}
            style={{
              fontSize: 12, color: 'var(--text-200)', background: 'none', border: 'none',
              cursor: 'pointer', padding: '4px 8px', borderRadius: 4,
            }}
          >
            新对话
          </button>
        </div>
      </div>

      {/* 消息列表 */}
      <div
        ref={scrollContainerRef}
        style={{ flex: '1 1 auto', minHeight: 0, overflowY: 'auto', overflowX: 'hidden', padding: '16px 24px' }}>
        {messages.length === 0 && (
          <div style={{ textAlign: 'center', color: 'var(--text-200)', paddingTop: 80 }}>
            <p style={{ fontSize: 18, marginBottom: 8 }}>向知识库提问</p>
            <p style={{ fontSize: 13 }}>支持自然语言查询和知识库管理</p>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} data-message-index={i} style={{
            marginBottom: 16,
            display: 'flex',
            flexDirection: 'column',
            alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
            minWidth: 0,  // 允许 flex 子项收缩
          }}>
            {/* 工具调用标签 */}
            {msg.toolCalls && msg.toolCalls.length > 0 && (
              <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 4 }}>
                {msg.toolCalls.map((tc, j) => (
                  <span key={j} className="tool-call-badge">{tc}</span>
                ))}
              </div>
            )}
            {/* 消息气泡 */}
            <div className={msg.role === 'assistant' ? 'assistant-bubble' : 'user-bubble'}
              style={{
                maxWidth: msg.role === 'user' ? '70%' : '90%',
                padding: '10px 16px',
                borderRadius: 12,
                background: msg.role === 'user' ? 'var(--primary-100)' : '#fff',
                color: msg.role === 'user' ? '#fff' : 'var(--text-100)',
                border: msg.role === 'assistant' ? '1px solid var(--bg-300)' : 'none',
                lineHeight: 1.6,
                minWidth: 0,
                overflowX: 'auto',
              }}>
              {msg.role === 'assistant' ? (
                <MessageContent text={msg.content} />
              ) : (
                <span style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</span>
              )}
            </div>
            {/* 追问建议 */}
            {msg.role === 'assistant' && msg.suggestedQuestions && msg.suggestedQuestions.length > 0 && (
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 6, maxWidth: '90%' }}>
                {msg.suggestedQuestions.map((q, j) => (
                  <button
                    key={j}
                    className="suggestion-btn"
                    onClick={() => handleSend(q)}
                    disabled={streaming}
                  >
                    {q}
                  </button>
                ))}
              </div>
            )}
            {/* 耗时/token 指标 */}
            {msg.role === 'assistant' && (msg.duration || msg.tokenCount) && (
              <div style={{ fontSize: 11, color: 'var(--text-200)', marginTop: 2 }}>
                {msg.duration && <span>{msg.duration}s</span>}
                {msg.duration && msg.tokenCount && <span> · </span>}
                {msg.tokenCount && <span>{msg.tokenCount} tokens</span>}
              </div>
            )}
          </div>
        ))}
        {/* 流式等待指示器 */}
        {streaming && elapsed > 0 && (
          <div style={{ fontSize: 11, color: 'var(--text-200)', textAlign: 'center', padding: '4px 0' }}>
            等待中... {formatElapsed(elapsed)}
          </div>
        )}
      </div>

      {/* 输入框 */}
      <div style={{ padding: '12px 24px', borderTop: '1px solid var(--bg-300)', flexShrink: 0 }}>
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSend()}
            placeholder="输入消息... (支持自然语言)"
            style={{
              flex: 1,
              padding: '10px 16px',
              borderRadius: 8,
              border: '1px solid var(--bg-300)',
              outline: 'none',
              fontSize: 14,
              background: '#fff',
            }}
          />
          <button
            onClick={streaming ? cancelStream : handleSend}
            style={{
              padding: '10px 20px',
              borderRadius: 8,
              border: 'none',
              background: streaming ? '#e53e3e' : 'var(--primary-100)',
              color: '#fff',
              fontWeight: 600,
              cursor: 'pointer',
              minWidth: 72,
            }}
          >
            {streaming ? '停止' : '发送'}
          </button>
        </div>
      </div>
    </div>
  )
}

/** 渲染消息内容 — Markdown + LaTeX + [[wikilink]] */
function MessageContent({ text }: { text: string }) {
  if (!text) return null

  // 预处理：移除 __SUGGESTIONS__ 行（学习模式追问标记）
  const cleaned = text.replace(/__SUGGESTIONS__\s*:\s*\[.*\]/s, '')
  // 预处理：[[wikilink]] → <span class="wikilink">name</span>
  const html = cleaned.replace(/\[\[([^\]]+)\]\]/g, '<span class="wikilink">$1</span>')

  return (
    <div className="chat-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeRaw, rehypeKatex]}
      >
        {html}
      </ReactMarkdown>
    </div>
  )
}
