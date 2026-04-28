import dotenv from "dotenv";
dotenv.config();

import express from "express";
import path from "path";
import cors from "cors";
import http from "http";
import MongoStore      from 'connect-mongo'
import session  from 'express-session'
import cookieParser     from 'cookie-parser'
import { Server } from "socket.io";
import helmet from 'helmet'
import mongoose from 'mongoose'

import db from "./src/config/db.js";
import relaySocket from "./src/socket/relay.js";
import { setIO } from "./src/socket/io.js";

import authRouter      from './src/routes/auth.js'
import queryRouter     from './src/routes/query.js'
import knowledgeRouter from './src/routes/knowledge.js'
import sessionRouter   from './src/routes/session.js'
import errorHandler from "./src/middleware/errorHandler.js";

// ── App + HTTP server ─────────────────────────────────────────────────────────
const app    = express();
const server = http.createServer(app);

const __dirname = new URL('.', import.meta.url).pathname;

app.use(express.urlencoded({ extended: true }));
app.use(cookieParser()) 
app.use(helmet())



// ── Middleware ─────────────────────────────────────────────────────────────
app.use(cors({
  origin:      process.env.CLIENT_URL || 'http://localhost:5173',
  credentials: true,   // required for cookies
}))
app.use(express.json())





// ── Request logger (dev only) ─────────────────────────────────────────────────
if (process.env.NODE_ENV !== 'production') {
  app.use((req, _res, next) => {
    console.log(`[HTTP] ${req.method} ${req.path}`);
    next();
  });
}




// ── Socket.IO ──────────────────────────────────────────────
export const io = new Server(server, {
  cors: {
    origin: process.env.CLIENT_URL || "https://multi-agent-decision-system.onrender.com",
    credentials: true,
  },
});

setIO(io);

io.on("connection", socket => {
  console.log("[ws] client connected:", socket.id);

  socket.on("join", sessionId => {
    socket.join(sessionId);
  });

  socket.on("disconnect", () => {
    console.log("[ws] client left:", socket.id);
  });
});




// ── Session (stored in MongoDB) ────────────────────────────────────────────
const IS_PROD = process.env.NODE_ENV === 'production'

if (IS_PROD) {
  app.set('trust proxy', 1)
}

if (IS_PROD && !process.env.SESSION_SECRET) {
  throw new Error('SESSION_SECRET is not set')
}

const MONGO_URI = process.env.MONGODB_URI || 'mongodb://localhost:27017/vantage'

app.set('trust proxy', 1)

app.use(session({
  name: 'vantage.sid',

  secret: process.env.SESSION_SECRET || 'vantage-session-secret-dev-only',

  resave: false,
  saveUninitialized: false,

  store: MongoStore.create({
    mongoUrl: MONGO_URI,
    collectionName: 'sessions',
    ttl: 7 * 24 * 60 * 60,
    autoRemove: 'native',
  }),

  cookie: {
    httpOnly: true,
    secure: IS_PROD,
    sameSite: IS_PROD ? 'none' : 'lax',
    maxAge: 7 * 24 * 60 * 60 * 1000,
  },
}))
 



// ── Routes ─────────────────────────────────────────────────────────────────────
app.use('/api/auth',      authRouter)
app.use('/api/query',     queryRouter)
app.use('/api/knowledge', knowledgeRouter)
app.use('/api/session',   sessionRouter)


// ── Health check ──────────────────────────────────────────────────────────────
app.get('/health', (_req, res) => {
  const states = {
    0: 'disconnected',
    1: 'connected',
    2: 'connecting',
    3: 'disconnecting',
  }

  res.json({
    status: 'ok',
    ts: new Date().toISOString(),
    uptime: Math.floor(process.uptime()),
    memMB: Math.round(process.memoryUsage().heapUsed / 1024 / 1024),
    mongoState: states[mongoose.connection.readyState] || 'unknown',
  })
})


// Serve static files
app.use(express.static(path.join(__dirname, "../client/dist")));

// Catch all routes → React app
app.use((req, res) => {
  res.sendFile(path.join(__dirname, "../client/dist/index.html"));
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





 
  server.listen(PORT, () => {
    console.log(`\n[Backend] Node.js backend running: port ${PORT}`);
  });
};
 
start();











