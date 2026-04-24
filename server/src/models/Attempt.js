
import mongoose from 'mongoose'
const AttemptSchema = new mongoose.Schema({
  commitHash:  { type: String, required: true, unique: true, index: true },
  sessionId:   { type: String, required: true, index: true },
  agentId:     { type: String, required: true },
  output:      { type: String, default: '' },
  score:       { type: Number, default: 0 },
  feedback:    { type: String, default: '' },
  status:      {
    type:    String,
    enum:    ['improved', 'regressed', 'baseline', 'crashed', 'timeout'],
    default: 'baseline',
  },
  parentHash:  { type: String, default: null },
  timestamp:   { type: Date, default: Date.now },
});
 
AttemptSchema.index({ sessionId: 1, score: -1 });
export default model('Attempt', AttemptSchema);