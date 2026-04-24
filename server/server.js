import dotenv from "dotenv";
dotenv.config();

import express from "express";
import path from "path";
import cors from "cors";
import http from "http";
import { Server } from "socket.io";

import db from "./src/config/db.js";
import relaySocket from "./src/socket/relay.js";

import queryRoutes from "./src/routes/query.routes.js";
import knowledgeRoutes from './src/routes/session.routes.js'
import sessionRoutes from "./src/routes/session.routes.js";
import errorHandler from "./src/middleware/errorHandler.js";

// ── App + HTTP server ─────────────────────────────────────────────────────────
const app    = express();
const server = http.createServer(app);
// ── CORS origins ──────────────────────────────────────────────────────────────
const allowedOrigins = (process.env.CORS_ORIGINS || 'http://localhost:5173')
  .split(',')
  .map((o) => o.trim());
 
app.use(cors({
  origin:      allowedOrigins,
  credentials: true,
}));

app.use(express.json());
app.use(express.urlencoded({ extended: true }));


const __dirname = new URL('.', import.meta.url).pathname;


// ── Request logger (dev only) ─────────────────────────────────────────────────
if (process.env.NODE_ENV !== 'production') {
  app.use((req, _res, next) => {
    console.log(`[HTTP] ${req.method} ${req.path}`);
    next();
  });
}



// ── Socket.IO ─────────────────────────────────────────────────────────────────
const io = new Server(server, {
  cors: {
    origin: allowedOrigins,
    methods: ["GET", "POST"],
  },
});

relaySocket(io);





// ── Routes ─────────────────────────────────────────────────────────────────────
app.use("/api/query", queryRoutes);
app.use("/api/knowledge", knowledgeRoutes);
app.use("/api/session", sessionRoutes);


// ── Health check ──────────────────────────────────────────────────────────────
app.get('/health', (_req, res) => {
  res.json({
    status:    'ok',
    service:   'decision-lab-backend',
    fastapi:   process.env.FASTAPI_URL || 'http://localhost:8000',
    timestamp: new Date().toISOString(),
  });
});
 


// ── Root ──────────────────────────────────────────────────────────────────────
app.get('/', (_req, res) => {
  res.json({
    service:   'Autonomous Decision Lab — Node.js Backend',
    version:   '1.0.0',
    endpoints: [
      'POST   /api/query',
      'GET    /api/query/stream/:sessionId',
      'GET    /api/query/status/:sessionId',
      'GET    /api/query/history',
      'GET    /api/knowledge/notes',
      'GET    /api/knowledge/skills',
      'GET    /api/knowledge/leaderboard',
      'GET    /api/session/:id',
      'PATCH  /api/session/:id',
      'DELETE /api/session/:id',
      'GET    /health',
    ],
  });
});



// ── 404 handler ───────────────────────────────────────────────────────────────
app.use((_req, res) => {
  res.status(404).json({ error: 'Route not found' });
});
 
// ── Global error handler ──────────────────────────────────────────────────────
app.use(errorHandler);
 
// ── Start ─────────────────────────────────────────────────────────────────────
const PORT = parseInt(process.env.PORT || '3001');
 
const start = async () => {
  await db();   // MongoDB (non-blocking — continues even if DB offline)



// Serve static files
app.use(express.static(path.join(__dirname, "../client/dist")));

// Catch all routes → React app
app.use((req, res) => {
  res.sendFile(path.join(__dirname, "../client/dist/index.html"));
});

 
  server.listen(PORT, () => {
    console.log(`\n[Backend] Node.js backend running`);
    console.log(`[Backend] http://localhost:${PORT}`);
    console.log(`[Backend] FastAPI target: ${process.env.FASTAPI_URL || 'http://localhost:8000'}`);
    console.log(`[Backend] CORS origins:   ${allowedOrigins.join(', ')}\n`);
  });
};
 
start();











