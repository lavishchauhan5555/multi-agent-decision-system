import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const TABS = ['leaderboard', 'notes', 'skills']

function LeaderboardTable({ data }) {
  if (!data?.length) return (
    <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-3)', fontSize: 12 }}>
      No leaderboard entries yet.
    </div>
  )
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, fontFamily: 'var(--mono)' }}>
        <thead>
          <tr style={{ borderBottom: '1px solid var(--border)' }}>
            {['#', 'QUERY', 'SCORE', 'DECISION', 'ROUNDS', 'DATE'].map(h => (
              <th key={h} style={{
                padding: '8px 12px', textAlign: 'left',
                color: 'var(--text-3)', fontSize: 10, letterSpacing: '0.12em', fontWeight: 600,
              }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr key={row._id || i} style={{
              borderBottom: '1px solid var(--border)',
              transition: 'background 0.1s',
            }}
              onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-2)'}
              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
            >
              <td style={{ padding: '10px 12px', color: i < 3 ? 'var(--amber)' : 'var(--text-3)' }}>
                {i < 3 ? ['◈', '◇', '○'][i] : i + 1}
              </td>
              <td style={{ padding: '10px 12px', color: 'var(--text-1)', maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {row.query}
              </td>
              <td style={{ padding: '10px 12px' }}>
                <span style={{
                  color: row.score >= 0.85 ? 'var(--green)' : row.score >= 0.7 ? 'var(--amber)' : 'var(--red)',
                  fontWeight: 700,
                }}>
                  {(row.score * 100).toFixed(0)}%
                </span>
              </td>
              <td style={{ padding: '10px 12px', color: 'var(--text-2)' }}>
                {row.decision || '—'}
              </td>
              <td style={{ padding: '10px 12px', color: 'var(--text-3)' }}>{row.rounds || '—'}</td>
              <td style={{ padding: '10px 12px', color: 'var(--text-3)', fontSize: 10 }}>
                {row.createdAt ? new Date(row.createdAt).toLocaleDateString() : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function NotesList({ data }) {
  const [selected, setSelected] = useState(null)
  if (!data?.length) return (
    <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-3)', fontSize: 12 }}>
      No notes captured yet. Run evaluations to generate reflections.
    </div>
  )
  return (
    <div style={{ display: 'grid', gridTemplateColumns: selected ? '260px 1fr' : '1fr', gap: 12, height: '100%' }}>
      <div style={{ overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 6 }}>
        {data.map((note, i) => (
          <button key={note._id || i}
            onClick={() => setSelected(selected?._id === note._id ? null : note)}
            style={{
              background: selected?._id === note._id ? 'var(--bg-3)' : 'var(--bg-2)',
              border: `1px solid ${selected?._id === note._id ? 'var(--border-lit)' : 'var(--border)'}`,
              borderRadius: 'var(--radius-sm)',
              padding: '10px 14px',
              textAlign: 'left',
              cursor: 'pointer',
              color: 'var(--text-1)',
              fontFamily: 'var(--mono)',
              fontSize: 11,
              transition: 'all 0.15s',
            }}
          >
            <div style={{ color: 'var(--amber)', fontSize: 10, marginBottom: 4 }}>
              {note.fileName || `note_${i + 1}.md`}
            </div>
            <div style={{ color: 'var(--text-3)', fontSize: 10 }}>
              {note.createdAt ? new Date(note.createdAt).toLocaleDateString() : ''}
            </div>
          </button>
        ))}
      </div>
      {selected && (
        <div className="panel" style={{ height: '100%', overflowY: 'auto' }}>
          <div className="panel-header">
            <span className="panel-label">{selected.fileName}</span>
            <button onClick={() => setSelected(null)} style={{ marginLeft: 'auto', background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', fontSize: 14 }}>✕</button>
          </div>
          <div className="panel-body" style={{ whiteSpace: 'pre-wrap', fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-2)', lineHeight: 1.7 }}>
            {selected.content || 'No content available.'}
          </div>
        </div>
      )}
    </div>
  )
}

function SkillsList({ data }) {
  const [selected, setSelected] = useState(null)
  if (!data?.length) return (
    <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-3)', fontSize: 12 }}>
      No skills consolidated yet.
    </div>
  )
  return (
    <div style={{ display: 'grid', gridTemplateColumns: selected ? '260px 1fr' : 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12 }}>
      {!selected && data.map((skill, i) => (
        <button key={skill._id || i}
          onClick={() => setSelected(skill)}
          style={{
            background: 'var(--bg-2)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)',
            padding: '16px',
            textAlign: 'left',
            cursor: 'pointer',
            transition: 'all 0.15s',
          }}
          onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--border-lit)'; e.currentTarget.style.background = 'var(--bg-3)' }}
          onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.background = 'var(--bg-2)' }}
        >
          <div style={{ color: 'var(--amber)', fontSize: 11, fontFamily: 'var(--mono)', marginBottom: 8 }}>
            ◈ {skill.name || `skill_${i + 1}`}
          </div>
          <div style={{ color: 'var(--text-2)', fontSize: 11, lineHeight: 1.5, marginBottom: 10 }}>
            {skill.description?.slice(0, 80) || 'No description'}...
          </div>
          <div style={{ color: 'var(--text-3)', fontSize: 10, fontFamily: 'var(--mono)' }}>
            {skill.scripts?.length || 0} scripts
          </div>
        </button>
      ))}
      {selected && (
        <>
          <div style={{ overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 6 }}>
            {data.map((skill, i) => (
              <button key={skill._id || i}
                onClick={() => setSelected(skill)}
                style={{
                  background: selected._id === skill._id ? 'var(--bg-3)' : 'var(--bg-2)',
                  border: `1px solid ${selected._id === skill._id ? 'var(--border-lit)' : 'var(--border)'}`,
                  borderRadius: 'var(--radius-sm)',
                  padding: '10px 14px', textAlign: 'left', cursor: 'pointer',
                  color: 'var(--amber)', fontFamily: 'var(--mono)', fontSize: 11,
                }}>
                {skill.name || `skill_${i + 1}`}
              </button>
            ))}
          </div>
          <div className="panel" style={{ height: '100%', overflowY: 'auto' }}>
            <div className="panel-header">
              <span className="panel-label">{selected.name}</span>
              <button onClick={() => setSelected(null)} style={{ marginLeft: 'auto', background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', fontSize: 14 }}>✕</button>
            </div>
            <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.6 }}>{selected.description}</div>
              {selected.scripts?.length > 0 && (
                <div>
                  <div className="data-dim" style={{ fontSize: 10, marginBottom: 6 }}>SCRIPTS</div>
                  {selected.scripts.map((s, si) => (
                    <div key={si} style={{ padding: '8px 12px', background: 'var(--bg-3)', borderRadius: 'var(--radius-sm)', fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text-2)', marginBottom: 4 }}>
                      {s}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}

export default function KnowledgeBrowser() {
  const { authFetch } = useAuth()
  const navigate = useNavigate()
  const [tab, setTab]           = useState('leaderboard')
  const [data, setData]         = useState({ notes: [], skills: [], leaderboard: [] })
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    Promise.all([
      authFetch('/api/knowledge/notes').then(r => r.json()),
      authFetch('/api/knowledge/skills').then(r => r.json()),
      authFetch('/api/knowledge/leaderboard').then(r => r.json()),
    ])
      .then(([notes, skills, leaderboard]) => setData({ notes, skills, leaderboard }))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg-0)' }}>
      {/* Topbar */}
      <div className="topbar">
        <span className="topbar-logo">VANTAGE</span>
        <span className="topbar-sep">/</span>
        <span className="topbar-sub">knowledge browser</span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <button className="btn" style={{ padding: '6px 14px', fontSize: 11 }} onClick={() => navigate('/')}>
            ↩ home
          </button>
        </div>
      </div>

      <div style={{ flex: 1, padding: '16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
        {/* Tabs */}
        <div style={{ display: 'flex', gap: 4, borderBottom: '1px solid var(--border)', paddingBottom: 0 }}>
          {TABS.map(t => (
            <button key={t} onClick={() => setTab(t)} style={{
              background: 'none',
              border: 'none',
              borderBottom: `2px solid ${tab === t ? 'var(--amber)' : 'transparent'}`,
              color: tab === t ? 'var(--amber)' : 'var(--text-3)',
              fontFamily: 'var(--mono)',
              fontSize: 11,
              letterSpacing: '0.12em',
              textTransform: 'uppercase',
              padding: '8px 16px',
              cursor: 'pointer',
              transition: 'all 0.15s',
              marginBottom: -1,
            }}>
              {t === 'leaderboard' ? '◈ leaderboard' : t === 'notes' ? '✦ notes' : '⟡ skills'}
            </button>
          ))}
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center' }}>
            {loading && <span className="data-dim" style={{ fontSize: 10 }}>loading…</span>}
          </div>
        </div>

        {error && (
          <div style={{ padding: '10px 14px', background: 'var(--red-dim)', border: '1px solid var(--red)', borderRadius: 'var(--radius-sm)', fontSize: 11, color: 'var(--red)' }}>
            ✕ {error}
          </div>
        )}

        {/* Stats row */}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {[
            { label: 'TOTAL RUNS', value: data.leaderboard.length },
            { label: 'NOTES', value: data.notes.length },
            { label: 'SKILLS', value: data.skills.length },
            { label: 'TOP SCORE', value: data.leaderboard[0] ? `${(data.leaderboard[0].score * 100).toFixed(0)}%` : '—' },
          ].map(stat => (
            <div key={stat.label} className="panel" style={{ flex: '1 1 120px' }}>
              <div className="panel-body" style={{ padding: '12px 16px' }}>
                <div className="data-dim" style={{ fontSize: 9, marginBottom: 4 }}>{stat.label}</div>
                <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-0)', fontFamily: 'var(--mono)' }}>
                  {stat.value}
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Content */}
        <div className="panel" style={{ flex: 1, overflow: 'hidden' }}>
          <div className="panel-body" style={{ padding: '12px', height: '100%', overflowY: 'auto' }}>
            {tab === 'leaderboard' && <LeaderboardTable data={data.leaderboard} />}
            {tab === 'notes'       && <NotesList data={data.notes} />}
            {tab === 'skills'      && <SkillsList data={data.skills} />}
          </div>
        </div>
      </div>
    </div>
  )
}