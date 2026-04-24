import express from "express";
import Session from "../models/Session.js";

const router = express.Router();

// ── GET /api/session/:id ─────────────────────────────────────────────────────
router.get("/:id", async (req, res) => {
  try {
    const session = await Session.findOne({
      sessionId: req.params.id,
    }).lean();

    if (!session) {
      return res.status(404).json({
        error: "Session not found",
      });
    }

    return res.json(session);
  } catch (err) {
    return res.status(500).json({
      error: err.message,
    });
  }
});

// ── PATCH /api/session/:id ───────────────────────────────────────────────────
router.patch("/:id", async (req, res) => {
  const allowed = [
    "status",
    "finalDecision",
    "confidenceScore",
    "debateRounds",
    "completedAt",
  ];

  const update = {};

  for (const key of allowed) {
    if (req.body[key] !== undefined) {
      update[key] = req.body[key];
    }
  }

  try {
    const session = await Session.findOneAndUpdate(
      { sessionId: req.params.id },
      { $set: update },
      { new: true }
    ).lean();

    if (!session) {
      return res.status(404).json({
        error: "Session not found",
      });
    }

    return res.json(session);
  } catch (err) {
    return res.status(500).json({
      error: err.message,
    });
  }
});

// ── DELETE /api/session/:id ──────────────────────────────────────────────────
router.delete("/:id", async (req, res) => {
  try {
    await Session.deleteOne({
      sessionId: req.params.id,
    });

    return res.json({
      deleted: true,
      sessionId: req.params.id,
    });
  } catch (err) {
    return res.status(500).json({
      error: err.message,
    });
  }
});

// ── GET /api/session ─────────────────────────────────────────────────────────
router.get("/", async (req, res) => {
  const limit = Math.min(parseInt(req.query.limit || "20"), 100);
  const skip = parseInt(req.query.skip || "0");

  try {
    const [sessions, total] = await Promise.all([
      Session.find({})
        .sort({ createdAt: -1 })
        .skip(skip)
        .limit(limit)
        .lean(),

      Session.countDocuments(),
    ]);

    return res.json({
      sessions,
      total,
      limit,
      skip,
    });
  } catch (err) {
    return res.status(500).json({
      error: err.message,
    });
  }
});

export default router;