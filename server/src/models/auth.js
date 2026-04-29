// models/index.js
import mongoose from 'mongoose'
const { Schema, model, models } = mongoose

// ── User ──────────────────────────────────────────────────────────────────
const userSchema = new mongoose.Schema({
  name: { type: String, required: true },
  email: { type: String, required: true, unique: true, lowercase: true },
  passwordHash: { type: String, required: true },
  role: { type: String, enum: ['operator', 'admin'], default: 'operator' },
}, { timestamps: true })


// ── RefreshToken (whitelist — stored in DB so we can revoke) ───────────────
const refreshTokenSchema = new mongoose.Schema({
  userId: { type: mongoose.Schema.Types.ObjectId, ref: 'User', required: true },
  tokenHash: { type: String, required: true, unique: true },  // SHA-256 of raw token
  expiresAt: { type: Date, required: true },
  userAgent: { type: String },
  ip: { type: String },
}, { timestamps: true })

// Auto-delete expired tokens
refreshTokenSchema.index({ expiresAt: 1 }, { expireAfterSeconds: 0 })


// ─────────────────────────────────────────────────────────────────────────────
// Session
// ─────────────────────────────────────────────────────────────────────────────
const SessionSchema = new Schema(
  {
    // ── sessionId: stable string mirror of _id ───────────────────────────────
    // default() runs at document construction time, before any hook,
    // so it is never null even if the caller omits it.
    sessionId: {
      type: String,
      unique: true,
      sparse: true,
      default: function () { return this._id?.toString() },
    },

    userId: { type: Schema.Types.ObjectId, ref: 'User', default: null },
    query: { type: String, required: true, trim: true },

    // Run config
    maxRounds: { type: Number, default: 3, min: 1, max: 20 },
    threshold: { type: Number, default: 0.85, min: 0, max: 1 },

    // Runtime state
    status: {
      type: String,
      enum: ['starting', 'running', 'done', 'error'],
      default: 'starting',
    },
    currentRound: { type: Number, default: 0 },
    confidenceScore: { type: Number, default: 0 },
    bestScore: { type: Number, default: 0 },
    heartbeatAction: { type: String, default: 'refine' },

    // Output
    finalDecision: { type: Schema.Types.Mixed, default: null },
    errorMsg: { type: String, default: null },
    completedAt: { type: Date, default: null },
  },
  { timestamps: true }
)


// ── Prompt (versioned system prompts) ─────────────────────────────────────
const promptSchema = new mongoose.Schema({
  agentId: { type: String, required: true },
  version: { type: Number, required: true },
  content: { type: String, required: true },
  score: { type: Number },
  active: { type: Boolean, default: true },
  promptType: {
    type: String,
    enum: ['base', 'eval', 'stuck'],
    default: 'base'
  },
}, { timestamps: true })

// ── Note (reflection notes from agents) ───────────────────────────────────
const noteSchema = new mongoose.Schema({
  fileName: { type: String },
  content: { type: String },
  sessionId: { type: mongoose.Schema.Types.ObjectId, ref: 'Session' },
  agentId: { type: String },
  tags: [{ type: String }],
}, { timestamps: true })

// ── Skill (consolidated reusable procedures) ──────────────────────────────
const skillSchema = new mongoose.Schema({
  name: { type: String, required: true },
  description: { type: String },
  scripts: [{ type: String }],
  connections: [{ type: String }],
  sessionId: { type: mongoose.Schema.Types.ObjectId, ref: 'Session' },
}, { timestamps: true })

// ── LeaderBoard entry ──────────────────────────────────────────────────────
const leaderboardSchema = new mongoose.Schema({
  sessionId: { type: mongoose.Schema.Types.ObjectId, ref: 'Session' },
  query: { type: String },
  score: { type: Number },
  decision: { type: String },
  rounds: { type: Number },
  agentId: { type: String },
  output: { type: mongoose.Schema.Types.Mixed },
  feedback: { type: String },
}, { timestamps: true })

export const User = mongoose.model('User', userSchema)
export const Session = models.Session ?? model('Session', SessionSchema)
export const Prompt = mongoose.model('Prompt', promptSchema)
export const Note = mongoose.model('Note', noteSchema)
export const Skill = mongoose.model('Skill', skillSchema)
export const Leaderboard = mongoose.model('Leaderboard', leaderboardSchema)
export const RefreshToken = mongoose.model('RefreshToken', refreshTokenSchema)
// export default model('User', userSchema);
// export default model('Session', sessionSchema);
// export default model('Prompt', promptSchema);
// export default model('Note', noteSchema);
// export default model('Skill', skillSchema);
// export default model('Leaderboard', leaderboardSchema);