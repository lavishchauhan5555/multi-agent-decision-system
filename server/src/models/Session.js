import mongoose from 'mongoose'
const SessionSchema = new mongoose.Schema({
  sessionId:  { type: String, required: true, unique: true, index: true },
  query:      { type: String, required: true },
  userId:     { type: String, default: 'anonymous' },
  status:     {
    type:    String,
    enum:    ['running', 'done', 'failed'],
    default: 'running',
  },
  finalDecision:    { type: String,  default: '' },
  confidenceScore:  { type: Number,  default: 0 },
  debateRounds:     { type: Number,  default: 0 },
  maxRounds:        { type: Number,  default: 3 },
  threshold:        { type: Number,  default: 0.85 },
  createdAt:        { type: Date,    default: Date.now },
  completedAt:      { type: Date },
});
 
// Index for fast history queries
SessionSchema.index({ createdAt: -1 });
SessionSchema.index({ userId: 1, createdAt: -1 });
 

export default mongoose.model('Session', SessionSchema);