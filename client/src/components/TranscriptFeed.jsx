// src/components/TranscriptFeed.jsx
import { useEffect, useRef, useState, useCallback } from 'react'

const NODE_COLORS = {
  cache_check_node: 'var(--blue)',
  fanout_node:      'var(--text-3)',
  research_node:    'var(--amber)',
  finance_node:     '#a0d080',
  competitor_node:  '#d080d0',
  critic_node:      'var(--red)',
  heartbeat_node:   '#60c0d0',
  ceo_node:         'var(--green)',
  meta_eval_node:   'var(--text-2)',
  cache_check:      'var(--blue)',
  fanout:           'var(--text-3)',
  research:         'var(--amber)',
  finance:          '#a0d080',
  competitor:       '#d080d0',
  critic:           'var(--red)',
  heartbeat:        '#60c0d0',
  ceo:              'var(--green)',
  meta_eval:        'var(--text-2)',
  __done__:         'var(--green)',
  __error__:        'var(--red)',
}

const NODE_SHORT = {
  cache_check_node: 'CACHE',
  fanout_node:      'FANOT',
  research_node:    'RSRCH',
  finance_node:     'FINCC',
  competitor_node:  'COMP',
  critic_node:      'CRIT',
  heartbeat_node:   'BEAT',
  ceo_node:         'CEO',
  meta_eval_node:   'META',
  cache_check:      'CACHE',
  fanout:           'FANOT',
  research:         'RSRCH',
  finance:          'FINCC',
  competitor:       'COMP',
  critic:           'CRIT',
  heartbeat:        'BEAT',
  ceo:              'CEO',
  meta_eval:        'META',
  __done__:         'DONE',
  __error__:        'ERR',
}

// ── Copy button ───────────────────────────────────────────────────────────────
function CopyButton({ text }) {
  const [copied, setCopied] = useState(false)
  const handle = (e) => {
    e.stopPropagation()
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }
  return (
    <button onClick={handle} style={{
      marginTop:    6,
      padding:      '2px 10px',
      fontSize:     10,
      fontFamily:   'var(--mono)',
      background:   'transparent',
      border:       '1px solid var(--border, rgba(255,255,255,0.12))',
      borderRadius: 3,
      color:        copied ? 'var(--green)' : 'var(--text-3)',
      cursor:       'pointer',
      letterSpacing:'0.08em',
      transition:   'color 0.2s',
    }}>
      {copied ? '✓ copied' : 'copy'}
    </button>
  )
}

// ── Single expandable event row ───────────────────────────────────────────────
function EventRow({ ev }) {
  const [expanded, setExpanded] = useState(false)

  const color      = NODE_COLORS[ev.node] ?? 'var(--text-2)'
  const short      = NODE_SHORT[ev.node]  ?? ev.node.slice(0, 5).toUpperCase()
  const isTerminal = ['__done__', '__error__'].includes(ev.node)
  const raw        = ev.content ?? ''
  const hasMore    = raw.length > 80 && !isTerminal

  const tsStr = ev.timestamp
    ? new Date(ev.timestamp * 1000).toLocaleTimeString('en-US', { hour12: false })
    : ''

  // Show only first line, truncated, as preview
  const firstLine = raw.split('\n').find(l => l.trim()) ?? ''
  const preview   = firstLine.slice(0, 80) + (raw.length > 80 ? '…' : '')

  const toggle = useCallback(() => {
    if (hasMore) setExpanded(e => !e)
  }, [hasMore])

  return (
    <div
      onClick={toggle}
      style={{
        borderLeft:  `2px solid ${expanded ? color : 'transparent'}`,
        background:  expanded ? 'rgba(255,255,255,0.025)' : 'transparent',
        cursor:      hasMore ? 'pointer' : 'default',
        transition:  'background 0.15s, border-color 0.15s',
      }}
    >
      {/* ── Header row (always visible) ────────────────────────────────── */}
      <div style={{
        display:             'grid',
        gridTemplateColumns: '58px 46px 12px 1fr',
        gap:                 '0 8px',
        padding:             '4px 12px',
        alignItems:          'center',
      }}>
        {/* Timestamp */}
        <span style={{ color: 'var(--text-3)', fontSize: 10, userSelect: 'none' }}>
          {tsStr}
        </span>

        {/* Node badge */}
        <span style={{ color, fontWeight: 700, fontSize: 10, letterSpacing: '0.08em' }}>
          {short}
        </span>

        {/* Chevron — only visible when expandable */}
        <span style={{
          color:      'var(--text-3)',
          fontSize:   8,
          userSelect: 'none',
          opacity:    hasMore ? 0.7 : 0,
          transform:  expanded ? 'rotate(90deg)' : 'rotate(0deg)',
          transition: 'transform 0.18s',
          display:    'inline-block',
        }}>
          ▶
        </span>

        {/* Preview text */}
        <span style={{
          color:        isTerminal ? color : 'var(--text-1)',
          fontSize:     11,
          fontFamily:   'var(--mono)',
          whiteSpace:   'nowrap',
          overflow:     'hidden',
          textOverflow: 'ellipsis',
        }}>
          {ev.node === '__done__'  && '■ run complete'}
          {ev.node === '__error__' && `✕ ${raw || 'unknown error'}`}
          {!isTerminal && (raw
            ? preview
            : <span style={{ color: 'var(--text-3)' }}>—</span>
          )}
        </span>
      </div>

      {/* ── Expanded full content ───────────────────────────────────────── */}
      {expanded && !isTerminal && (
        <div
          onClick={e => e.stopPropagation()}   // clicks inside don't collapse
          style={{
            padding:   '8px 12px 10px 124px',
            borderTop: '1px solid rgba(255,255,255,0.06)',
          }}
        >
          <pre style={{
            margin:     0,
            fontFamily: 'var(--mono)',
            fontSize:   11,
            lineHeight: 1.65,
            color:      'var(--text-1)',
            whiteSpace: 'pre-wrap',
            wordBreak:  'break-word',
            maxHeight:  400,
            overflowY:  'auto',
            background: 'transparent',
          }}>
            {raw}
          </pre>
          <CopyButton text={raw} />
        </div>
      )}
    </div>
  )
}

// ── Feed container ────────────────────────────────────────────────────────────
export default function TranscriptFeed({ events = [] }) {
  const bottomRef    = useRef(null)
  const containerRef = useRef(null)
  const [autoScroll, setAutoScroll] = useState(true)

  useEffect(() => {
    if (autoScroll) bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events.length, autoScroll])

  const handleScroll = () => {
    const el = containerRef.current
    if (!el) return
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40
    setAutoScroll(nearBottom)
  }

  return (
    <div className="panel" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>

      {/* Header */}
      <div className="panel-header" style={{ justifyContent: 'space-between' }}>
        <span className="panel-label">Event Stream</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {!autoScroll && (
            <button
              onClick={() => {
                setAutoScroll(true)
                bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
              }}
              style={{
                fontSize:     9,
                fontFamily:   'var(--mono)',
                background:   'transparent',
                border:       '1px solid var(--border)',
                color:        'var(--amber)',
                padding:      '2px 8px',
                cursor:       'pointer',
                borderRadius: 3,
                letterSpacing:'0.08em',
              }}
            >
              ↓ resume
            </button>
          )}
          <span className="data-dim" style={{ fontSize: 10 }}>
            {events.length} events
          </span>
        </div>
      </div>

      {/* Scrollable event list */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        style={{ flex: 1, overflowY: 'auto', padding: '4px 0' }}
      >
        {events.length === 0 && (
          <div style={{
            padding:   '24px 16px',
            color:     'var(--text-3)',
            textAlign: 'center',
            fontSize:  11,
            fontFamily:'var(--mono)',
          }}>
            Awaiting agent events…
          </div>
        )}

        {events.map((ev, i) => <EventRow key={i} ev={ev} />)}

        <div ref={bottomRef} />
      </div>
    </div>
  )
}