/**
 * src/test_backend.js
 * ────────────────────
 * Test suite for Phase 5 Node.js backend.
 *
 * Usage:
 *   node src/test_backend.js
 *   ONLINE=1 node src/test_backend.js
 */

import dotenv from "dotenv";
dotenv.config();

import http from "http";
import path from "path";
import fs from "fs";
import { fileURLToPath } from "url";

import pkg from "../package.json" assert { type: "json" };

// ── ESM __dirname replacement ────────────────────────────────────────────────
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// ── Config ───────────────────────────────────────────────────────────────────
const ONLINE = process.env.ONLINE === "1";
const NODE_URL = `http://localhost:${process.env.PORT || 3001}`;

let passed = 0;
let failed = 0;

function pass(msg) {
  console.log(`   PASS — ${msg}`);
  passed++;
}

function fail(msg) {
  console.log(`   FAIL — ${msg}`);
  failed++;
}

function skip(msg) {
  console.log(`   SKIP — ${msg}`);
}

function head(msg) {
  console.log(`\n── ${msg} ──`);
}

// ── Helper: HTTP GET ─────────────────────────────────────────────────────────
function httpGet(url) {
  return new Promise((resolve, reject) => {
    http.get(url, (res) => {
      let body = "";

      res.on("data", (chunk) => {
        body += chunk;
      });

      res.on("end", () => {
        try {
          resolve({
            status: res.statusCode,
            data: JSON.parse(body),
          });
        } catch {
          resolve({
            status: res.statusCode,
            data: body,
          });
        }
      });
    }).on("error", reject);
  });
}

// ── Helper: HTTP POST ────────────────────────────────────────────────────────
function httpPost(url, body) {
  return new Promise((resolve, reject) => {
    const payload = JSON.stringify(body);

    const opts = {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Content-Length": Buffer.byteLength(payload),
      },
    };

    const req = http.request(url, opts, (res) => {
      let data = "";

      res.on("data", (chunk) => {
        data += chunk;
      });

      res.on("end", () => {
        try {
          resolve({
            status: res.statusCode,
            data: JSON.parse(data),
          });
        } catch {
          resolve({
            status: res.statusCode,
            data,
          });
        }
      });
    });

    req.on("error", reject);
    req.write(payload);
    req.end();
  });
}

// ── Test 1: File structure ───────────────────────────────────────────────────
function test_file_structure() {
  head("Test 1: file structure");

  const required = [
    "src/app.js",
    "src/config/db.js",
    "src/models/Session.js",
    "src/models/Attempt.js",
    "src/models/Prompt.js",
    "src/routes/query.routes.js",
    "src/routes/knowledge.routes.js",
    "src/routes/session.routes.js",
    "src/socket/relay.js",
    "src/middleware/errorHandler.js",
    "package.json",
    ".env",
  ];

  const root = path.join(__dirname, "..");

  let ok = true;

  for (const f of required) {
    const full = path.join(root, f);

    if (fs.existsSync(full)) {
      pass(`${f} exists`);
    } else {
      fail(`${f} MISSING`);
      ok = false;
    }
  }

  return ok;
}

// ── Test 2: package.json dependencies ───────────────────────────────────────
function test_package_json() {
  head("Test 2: package.json dependencies");

  const required = [
    "express",
    "socket.io",
    "axios",
    "mongoose",
    "cors",
    "dotenv",
    "eventsource",
  ];

  let ok = true;

  for (const dep of required) {
    if (pkg.dependencies?.[dep]) {
      pass(`${dep} listed`);
    } else {
      fail(`${dep} MISSING from dependencies`);
      ok = false;
    }
  }

  return ok;
}

// ── Test 3: model schemas load ──────────────────────────────────────────────
async function test_models_load() {
  head("Test 3: Mongoose models load without DB");

  const models = ["Session", "Attempt", "Prompt"];
  let ok = true;

  for (const m of models) {
    try {
      const module = await import(`./models/${m}.js`);
      const Model = module.default;

      if (Model?.modelName) {
        pass(`${m}.js loaded — modelName="${Model.modelName}"`);
      } else {
        fail(`${m}.js loaded but no modelName`);
        ok = false;
      }
    } catch (e) {
      fail(`${m}.js failed: ${e.message}`);
      ok = false;
    }
  }

  return ok;
}

// ── Test 4: env variables ───────────────────────────────────────────────────
function test_env() {
  head("Test 4: environment variables");

  const vars = {
    FASTAPI_URL: process.env.FASTAPI_URL,
    PORT: process.env.PORT,
    MONGODB_URI: process.env.MONGODB_URI,
  };

  let ok = true;

  for (const [k, v] of Object.entries(vars)) {
    if (v) {
      pass(`${k} = ${k === "MONGODB_URI" ? "***" : v}`);
    } else {
      fail(`${k} not set in .env`);
      ok = false;
    }
  }

  return ok;
}

// ── Test 5: routes load ──────────────────────────────────────────────────────
async function test_routes_load() {
  head("Test 5: Express routers load");

  const routes = [
    "./routes/query.routes.js",
    "./routes/knowledge.routes.js",
    "./routes/session.routes.js",
  ];

  let ok = true;

  for (const r of routes) {
    try {
      const module = await import(r);
      const router = module.default;

      if (typeof router === "function" || router?.stack) {
        pass(`${r} loaded`);
      } else {
        fail(`${r} did not export a router`);
        ok = false;
      }
    } catch (e) {
      fail(`${r} failed: ${e.message}`);
      ok = false;
    }
  }

  return ok;
}

// ── Test 6: Online — health check ───────────────────────────────────────────
async function test_health_online() {
  head("Test 6: GET /health");

  if (!ONLINE) {
    skip("set ONLINE=1 to run live tests");
    return true;
  }

  try {
    const { status, data } = await httpGet(`${NODE_URL}/health`);

    if (status === 200 && data.status === "ok") {
      pass(`/health returned 200`);
      return true;
    }

    fail(`/health returned status=${status}`);
    return false;
  } catch (e) {
    fail(`Could not reach server: ${e.message}`);
    return false;
  }
}

// ── Test 7: Online — POST /api/query ────────────────────────────────────────
async function test_post_query_online() {
  head("Test 7: POST /api/query");

  if (!ONLINE) {
    skip("set ONLINE=1 to run live tests");
    return true;
  }

  try {
    const { status, data } = await httpPost(
      `${NODE_URL}/api/query`,
      {
        query: "Should I start an AI SaaS in resume tools?",
        max_rounds: 1,
      }
    );

    if (status === 200 && data.sessionId) {
      pass(`POST /api/query → sessionId=${data.sessionId}`);
      return true;
    }

    fail(`POST /api/query failed`);
    return false;
  } catch (e) {
    fail(`POST error: ${e.message}`);
    return false;
  }
}

// ── Runner ───────────────────────────────────────────────────────────────────
async function run_all() {
  console.log("\n══════════════════════════════════════════");
  console.log("  Phase 5 — Node.js backend test suite");
  console.log(`  Mode: ${ONLINE ? "ONLINE" : "OFFLINE"}`);
  console.log("══════════════════════════════════════════");

  const results = [
    test_file_structure(),
    test_package_json(),
    await test_models_load(),
    test_env(),
    await test_routes_load(),
    await test_health_online(),
    await test_post_query_online(),
  ];

  const total = results.length;
  const nPass = results.filter(Boolean).length;

  console.log("\n── Summary ──");
  console.log(`   ${nPass}/${total} tests passed`);

  if (nPass === total) {
    console.log("\n   Phase 5 ready.");
    console.log("   Start: npm run dev");
  } else {
    console.log("\n   Fix failures above.");
    process.exit(1);
  }
}

run_all();