import dotenv from "dotenv";
dotenv.config();

import express from "express";
import path from "path";
import cors from "cors";
import http from "http";
import { Server } from "socket.io";
import { fileURLToPath } from "url";

import db from "./src/config/db.js";
import relaySocket from "./src/socket/relay.js";

import queryRoutes from "./src/routes/query.routes.js";
import knowledgeRoutes from "./src/routes/knowledge.routes.js";
import sessionRoutes from "./src/routes/session.routes.js";
import errorHandler from "./src/middleware/errorHandler.js";

const app = express();
const server = http.createServer(app);

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const allowedOrigins = (process.env.CORS_ORIGINS || "http://localhost:5173")
  .split(",")
  .map((o) => o.trim());

app.use(
  cors({
    origin: allowedOrigins,
    credentials: true,
  })
);

app.use(express.json());
app.use(express.urlencoded({ extended: true }));

if (process.env.NODE_ENV !== "production") {
  app.use((req, _res, next) => {
    console.log(`[HTTP] ${req.method} ${req.path}`);
    next();
  });
}

const io = new Server(server, {
  cors: {
    origin: allowedOrigins,
    methods: ["GET", "POST"],
  },
});

relaySocket(io);

// API routes
app.use("/api/query", queryRoutes);
app.use("/api/knowledge", knowledgeRoutes);
app.use("/api/session", sessionRoutes);

app.get("/health", (_req, res) => {
  res.json({
    status: "ok",
    service: "decision-lab-backend",
    fastapi: process.env.FASTAPI_URL || "http://localhost:8000",
    timestamp: new Date().toISOString(),
  });
});

app.get("/api", (_req, res) => {
  res.json({
    service: "Autonomous Decision Lab — Node.js Backend",
    version: "1.0.0",
    endpoints: [
      "POST   /api/query",
      "GET    /api/query/stream/:sessionId",
      "GET    /api/query/status/:sessionId",
      "GET    /api/query/history",
      "GET    /api/knowledge/notes",
      "GET    /api/knowledge/skills",
      "GET    /api/knowledge/leaderboard",
      "GET    /api/session/:id",
      "PATCH  /api/session/:id",
      "DELETE /api/session/:id",
      "GET    /health",
    ],
  });
});

// Serve React frontend
const clientDistPath = path.join(__dirname, "../client/dist");

app.use(express.static(clientDistPath));

app.get("*", (_req, res) => {
  res.sendFile(path.join(clientDistPath, "index.html"));
});

// API 404
app.use("/api", (_req, res) => {
  res.status(404).json({ error: "API route not found" });
});

app.use(errorHandler);

const PORT = parseInt(process.env.PORT || "3001", 10);

const start = async () => {
  await db();

  server.listen(PORT, () => {
    console.log("\n[Backend] Node.js backend running");
    console.log(`[Backend] http://localhost:${PORT}`);
    console.log(
      `[Backend] FastAPI target: ${
        process.env.FASTAPI_URL || "http://localhost:8000"
      }`
    );
    console.log(`[Backend] CORS origins: ${allowedOrigins.join(", ")}\n`);
  });
};

start();