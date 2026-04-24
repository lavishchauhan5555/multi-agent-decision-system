/**
 * socket/relay.js
 * ────────────────
 * Socket.IO relay — bridges FastAPI SSE stream to React client.
 */

import { EventSource } from "eventsource";

const FASTAPI = process.env.FASTAPI_URL || "http://localhost:8000";

export default function setupSocketRelay(io) {
  io.on("connection", (socket) => {
    console.log(`[Socket] Client connected: ${socket.id}`);

    // Map of sessionId -> EventSource
    const activeSources = {};

    // ── Client subscribes ────────────────────────────────────────────────
    socket.on("subscribe", ({ sessionId }) => {
      if (!sessionId) {
        socket.emit("stream_error", {
          message: "sessionId required",
        });
        return;
      }

      // Close existing stream
      if (activeSources[sessionId]) {
        activeSources[sessionId].close();
        delete activeSources[sessionId];
      }

      console.log(
        `[Socket] Subscribing ${socket.id} to session ${sessionId}`
      );

      const streamUrl = `${FASTAPI}/stream/${sessionId}`;
      const es = new EventSource(streamUrl);

      activeSources[sessionId] = es;

      // ── Relay SSE messages ─────────────────────────────────────────────
      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          const nodeName = data.node || "unknown";

          socket.emit("agent_event", {
            sessionId,
            node: nodeName,
            round: data.round || 0,
            data: data.data || data,
            timestamp: data.timestamp || Date.now() / 1000,
          });

          // Done signal
          if (nodeName === "__done__") {
            socket.emit("stream_done", { sessionId });

            es.close();
            delete activeSources[sessionId];

            console.log(
              `[Socket] Stream done for session ${sessionId}`
            );
          }

          // FastAPI error signal
          if (nodeName === "__error__") {
            socket.emit("stream_error", {
              message:
                data.data?.error || "Unknown FastAPI error",
            });

            es.close();
            delete activeSources[sessionId];
          }
        } catch (parseErr) {
          console.error(
            "[Socket] Failed to parse SSE event:",
            parseErr.message
          );
        }
      };

      // ── SSE error handler ──────────────────────────────────────────────
      es.onerror = (err) => {
        console.error(
          `[Socket] SSE error for session ${sessionId}:`,
          err?.message || err
        );

        socket.emit("stream_error", {
          message: `Lost connection to orchestrator for session ${sessionId}`,
        });

        es.close();
        delete activeSources[sessionId];
      };
    });

    // ── Manual unsubscribe ───────────────────────────────────────────────
    socket.on("unsubscribe", ({ sessionId }) => {
      if (activeSources[sessionId]) {
        activeSources[sessionId].close();
        delete activeSources[sessionId];

        console.log(
          `[Socket] Unsubscribed ${socket.id} from ${sessionId}`
        );
      }
    });

    // ── Disconnect cleanup ───────────────────────────────────────────────
    socket.on("disconnect", () => {
      console.log(`[Socket] Client disconnected: ${socket.id}`);

      for (const [sid, es] of Object.entries(activeSources)) {
        es.close();
        delete activeSources[sid];
      }
    });
  });
}