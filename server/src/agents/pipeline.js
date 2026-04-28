// agents/pipeline.js

import { Session, Leaderboard } from '../models/auth.js'
import { emitToSession } from '../routes/query.js'

const FASTAPI = process.env.FASTAPI_URL || 'http://localhost:8000'
const sleep = ms => new Promise(r => setTimeout(r, ms))

const emitAgentUpdate = (sid, agentId, status, output = null) =>
  emitToSession(sid, 'agent_update', { agentId, status, output, ts: Date.now() })

const emitTranscript = (sid, entry) =>
  emitToSession(sid, 'transcript', entry)

async function startFastAPIRun(session) {
  const res = await fetch(`${FASTAPI}/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query: session.query,
      max_rounds: session.maxRounds,
      threshold: session.threshold,
    }),
  })

  if (!res.ok) {
    const text = await res.text()
    throw new Error(`FastAPI /run failed [${res.status}]: ${text}`)
  }

  const data = await res.json()
  return data.session_id
}

async function consumeSSEStream(fastapiSessionId, mongoSessionId, update) {
  const res = await fetch(`${FASTAPI}/stream/${fastapiSessionId}`, {
    headers: { Accept: 'text/event-stream' },
  })

  if (!res.ok) {
    const text = await res.text()
    throw new Error(`FastAPI /stream failed [${res.status}]: ${text}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  let confidence = 0
  let bestScore = 0
  let round = 0
  let heartbeat = 'refine'
  let finalDecision = null

  while (true) {
    const { value, done } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })

    const frames = buffer.split('\n\n')
    buffer = frames.pop() || ''

    for (const frame of frames) {
      const dataLine = frame
        .split('\n')
        .find(line => line.startsWith('data:'))

      if (!dataLine) continue

      let parsed
      try {
        parsed = JSON.parse(dataLine.replace(/^data:\s*/, ''))
      } catch {
        continue
      }

      const {
        node,
        round: eventRound,
        timestamp,
        data,
      } = parsed

      if (!node) continue

      emitToSession(mongoSessionId, 'graph_event', {
        node,
        round: eventRound,
        timestamp,
        data,
      })

      if (eventRound != null) {
        round = eventRound
        await update({ currentRound: round })
      }

      if (data?.confidence_score != null) {
        confidence = data.confidence_score
        bestScore = Math.max(bestScore, confidence)
        await update({ confidenceScore: confidence, bestScore })
      }

      if (data?.best_score != null) {
        bestScore = Math.max(bestScore, data.best_score)
        await update({ bestScore })
      }

      if (data?.heartbeat_action) {
        heartbeat = data.heartbeat_action
        await update({ heartbeatAction: heartbeat })
      }

      if (data?.final_decision) {
        finalDecision = data.final_decision
        await update({ finalDecision })
      }

      if (node === '__done__') {
        return { confidence, bestScore, round, heartbeat, finalDecision }
      }

      if (node === '__error__') {
        throw new Error(data?.error ?? 'Unknown FastAPI graph error')
      }

      if (node === '__timeout__') {
        throw new Error(data?.error ?? 'FastAPI stream timeout')
      }
    }
  }

  return { confidence, bestScore, round, heartbeat, finalDecision }
}

async function pollFinalStatus(fastapiSessionId) {
  const res = await fetch(`${FASTAPI}/status/${fastapiSessionId}`)
  if (!res.ok) return null
  return res.json()
}

async function runStubPipeline(session, sid, update) {
  console.warn('[pipeline] FastAPI unreachable — running stub pipeline')

  const parallelAgents = ['research', 'finance', 'competitor', 'critic']
  let confidence = 0
  let bestScore = 0
  let heartbeat = 'refine'
  let finalDecision = null
  let round = 0

  for (round = 1; round <= session.maxRounds; round++) {
    await update({ currentRound: round, heartbeatAction: 'refine' })

    emitTranscript(sid, {
      role: 'system',
      text: `=== Round ${round} ===`,
      ts: Date.now(),
    })

    for (const agentId of parallelAgents) {
      emitAgentUpdate(sid, agentId, 'thinking')
      await sleep(200)

      const output = { summary: `[stub] ${agentId} analysis – round ${round}` }

      emitAgentUpdate(sid, agentId, 'done', output)
      emitTranscript(sid, {
        role: agentId,
        text: output.summary,
        ts: Date.now(),
      })
    }

    emitAgentUpdate(sid, 'ceo', 'thinking')
    await sleep(200)

    confidence = Math.min(0.99, confidence + 0.15 + Math.random() * 0.1)
    bestScore = Math.max(bestScore, confidence)

    heartbeat =
      confidence >= session.threshold
        ? 'exit'
        : round >= session.maxRounds
          ? 'pivot'
          : 'refine'

    finalDecision = {
      recommendation: 'PROCEED',
      summary: `[stub] CEO decision for "${session.query}" — round ${round}`,
      confidence,
      heartbeatAction: heartbeat,
    }

    emitAgentUpdate(sid, 'ceo', 'done', finalDecision)

    emitTranscript(sid, {
      role: 'ceo',
      text: finalDecision.summary,
      ts: Date.now(),
    })

    await update({
      confidenceScore: confidence,
      bestScore,
      heartbeatAction: heartbeat,
    })

    if (heartbeat === 'exit' || confidence >= session.threshold) break
  }

  return { confidence, bestScore, round, heartbeat, finalDecision }
}

export async function runAgentPipeline(session, { io, sseClients }) {
  const sid = session._id.toString()

  const update = async patch => {
    await Session.findByIdAndUpdate(session._id, patch)
    emitToSession(sid, 'state_update', patch)
  }

  try {
    await update({ status: 'running' })

    emitTranscript(sid, {
      role: 'system',
      text: `Pipeline started for: "${session.query}"`,
      ts: Date.now(),
    })

    let result
    let usedStub = false

    try {
      const fastapiSessionId = await startFastAPIRun(session)
      console.log(`[pipeline] FastAPI run started → session_id: ${fastapiSessionId}`)

      result = await consumeSSEStream(fastapiSessionId, sid, update)

      if (!result.finalDecision) {
        console.warn('[pipeline] Stream ended without finalDecision — polling /status')
        const statusData = await pollFinalStatus(fastapiSessionId)

        if (statusData) {
          result.finalDecision = statusData.finalDecision ?? result.finalDecision
          result.confidence = statusData.confidence ?? result.confidence
          result.round = statusData.currentRound ?? result.round
        }
      }
    } catch (fastApiErr) {
      console.error('[pipeline] FastAPI error:', fastApiErr.message)
      result = await runStubPipeline(session, sid, update)
      usedStub = true
    }

    const {
      confidence = 0,
      bestScore = 0,
      round = 0,
      finalDecision,
    } = result

    const safeDecision =
      finalDecision ?? {
        recommendation: 'INCONCLUSIVE',
        summary: 'Run completed but no final decision was produced.',
        confidence,
      }

    await Leaderboard.create({
      sessionId: session._id,
      query: session.query,
      score: confidence,
      decision: safeDecision.recommendation ?? 'UNKNOWN',
      rounds: round,
      output: safeDecision,
      stub: usedStub,
    })

    const completedAt = new Date()

    await update({
      status: 'done',
      finalDecision: safeDecision,
      currentRound: round,
      confidenceScore: confidence,
      bestScore,
      completedAt,
    })

    emitToSession(sid, 'done', {
      finalDecision: safeDecision,
      confidence,
    })

    emitTranscript(sid, {
      role: 'system',
      text: `✓ Run complete. Confidence: ${(confidence * 100).toFixed(0)}% ${usedStub ? '(stub)' : ''}`,
      ts: Date.now(),
    })
  } catch (err) {
    console.error('[pipeline]', err)

    await update({
      status: 'error',
      errorMsg: err.message,
    })

    emitToSession(sid, 'error', {
      message: err.message,
    })

    throw err
  }
}