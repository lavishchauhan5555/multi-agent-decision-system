import express from "express";
import axios from "axios";

const router = express.Router();

const FASTAPI = process.env.FASTAPI_URL || "http://localhost:8000";

// ── Generic proxy helper ────────────────────────────────────────────────────
const proxyGet = (path) => async (req, res) => {
  try {
    const params = req.query;

    const { data } = await axios.get(`${FASTAPI}${path}`, {
      params,
      timeout: 8000,
    });

    return res.json(data);
  } catch (err) {
    const msg = err.response?.data?.detail || err.message;

    console.error(`[knowledge] ${path} failed:`, msg);

    return res.status(502).json({
      error: msg,
    });
  }
};

// ── Routes ───────────────────────────────────────────────────────────────────
router.get("/notes", proxyGet("/knowledge/notes"));

router.get("/skills", proxyGet("/knowledge/skills"));

router.get("/leaderboard", proxyGet("/knowledge/leaderboard"));

// ── Session-specific leaderboard ────────────────────────────────────────────
router.get("/leaderboard/:sessionId", async (req, res) => {
  const { sessionId } = req.params;
  const top_k = req.query.top_k || 10;

  try {
    const { data } = await axios.get(
      `${FASTAPI}/knowledge/leaderboard`,
      {
        params: { top_k },
        timeout: 8000,
      }
    );

    const filtered = (data.attempts || []).filter(
      (attempt) => attempt.session_id === sessionId
    );

    return res.json({
      attempts: filtered,
    });
  } catch (err) {
    return res.status(502).json({
      error: err.message,
    });
  }
});

export default router;