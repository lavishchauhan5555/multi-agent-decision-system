/**
 * routes/query.routes.js
 * ───────────────────────
 * POST /api/query          — start a new agent run
 * GET  /api/query/stream/:sessionId — proxy SSE from FastAPI to client
 * GET  /api/query/status/:sessionId — check run status
 * GET  /api/query/history  — list past sessions from MongoDB
 *
 * All requests are forwarded to FastAPI (port 8000).
 * MongoDB is used to persist session records for history.
 */

import express from 'express'
import axios from 'axios'
const router   = express.Router();
import Session from "../models/Session.js";

const FASTAPI = process.env.FASTAPI_URL || 'http://localhost:8000';

// ── Helper: safe MongoDB upsert (skips if DB not connected) ─────────────────
const safeUpsert = async (Model, filter, update) => {
  try {
    await Model.findOneAndUpdate(filter, update, { upsert: true, new: true });
  } catch (_) {
    // DB not connected — skip silently in dev
  }
};

// ── POST /api/query ──────────────────────────────────────────────────────────
router.post('/', async (req, res) => {
  const { query, max_rounds = 2, threshold = 0.75  } = req.body;

  if (!query || !query.trim()) {
    return res.status(400).json({ error: 'query is required' });
  }

  try {
    // Forward to FastAPI
    const { data } = await axios.post(`${FASTAPI}/run`, {
      query,
      max_rounds,
      threshold,
    }, { timeout: 1000 });

    const sessionId = data.session_id;

    // Persist to MongoDB (non-blocking)
    await safeUpsert(
      Session,
      { sessionId },
      {
        sessionId,
        query:     query.trim(),
        userId:    req.headers['x-user-id'] || 'anonymous',
        status:    'running',
        maxRounds: max_rounds,
        threshold,
        createdAt: new Date(),
      }
    );

    return res.json({
      sessionId,
      status:    'started',
      streamUrl: `/api/query/stream/${sessionId}`,
    });

  } catch (err) {
    const msg = err.response?.data?.detail || err.message;
    console.error('[query] POST /api/query failed:', msg);
    return res.status(502).json({ error: `Orchestrator error: ${msg}` });
  }
});

// ── GET /api/query/stream/:sessionId ────────────────────────────────────────
// Proxies SSE stream from FastAPI to the browser.
// React uses EventSource('/api/query/stream/:id') to receive live events.
router.get('/stream/:sessionId', async (req, res) => {
  const { sessionId } = req.params;

  res.setHeader('Content-Type',  'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection',    'keep-alive');
  res.setHeader('X-Accel-Buffering', 'no');
  res.flushHeaders();

  try {
    const upstreamUrl = `${FASTAPI}/stream/${sessionId}`;

    const upstream = await axios.get(upstreamUrl, {
      responseType: 'stream',
      timeout:      0,   // no timeout for streaming
    });

    // Pipe FastAPI SSE directly to client
    upstream.data.pipe(res);

    // On client disconnect — kill upstream
    req.on('close', () => {
      upstream.data.destroy();
    });

    upstream.data.on('end', async () => {
      // Mark session done in MongoDB
      await safeUpsert(
        Session,
        { sessionId },
        { status: 'done', completedAt: new Date() }
      );
      res.end();
    });

    upstream.data.on('error', (err) => {
      console.error('[stream] Upstream error:', err.message);
      res.write(`data: ${JSON.stringify({ node: '__error__', data: { error: err.message } })}\n\n`);
      res.end();
    });

  } catch (err) {
    const msg = err.response?.data?.detail || err.message;
    console.error('[stream] Failed to connect to FastAPI:', msg);
    res.write(`data: ${JSON.stringify({ node: '__error__', data: { error: msg } })}\n\n`);
    res.end();
  }
});

// ── GET /api/query/status/:sessionId ─────────────────────────────────────────
router.get('/status/:sessionId', async (req, res) => {
  const { sessionId } = req.params;

  try {
    // Check FastAPI first (live status)
    const { data } = await axios.get(`${FASTAPI}/status/${sessionId}`, {
      timeout: 5000,
    });

    // Also get MongoDB record if available
    let dbRecord = null;
    try {
      dbRecord = await Session.findOne({ sessionId }).lean();
    } catch (_) {}

    return res.json({
      sessionId,
      active:    data.active,
      queueSize: data.queue_size,
      db:        dbRecord,
    });

  } catch (err) {
    return res.status(404).json({
      sessionId,
      active: false,
      error:  err.message,
    });
  }
});

// ── GET /api/query/history ─────────────────────────────────────────────────
router.get('/history', async (req, res) => {
  const limit  = Math.min(parseInt(req.query.limit  || '20'), 100);
  const skip   = parseInt(req.query.skip  || '0');
  const userId = req.query.userId || req.headers['x-user-id'];

  try {
    const filter = userId ? { userId } : {};
    const sessions = await Session
      .find(filter)
      .sort({ createdAt: -1 })
      .skip(skip)
      .limit(limit)
      .lean();

    return res.json({ sessions, total: sessions.length });

  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
});

export default router