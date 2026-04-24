import mongoose from 'mongoose'
const PromptSchema = new mongoose.Schema({
  agentId:   { type: String, required: true, index: true },
  version:   { type: Number, default: 1 },
  content:   { type: String, required: true },
  active:    { type: Boolean, default: true },
  score:     { type: Number, default: 0 },    // quality score from evaluator
  updatedAt: { type: Date, default: Date.now },
});
 
// Only one active prompt per agentId at a time
PromptSchema.index({ agentId: 1, active: 1 });
PromptSchema.index({ agentId: 1, version: -1 });
export default model('Prompt', PromptSchema);