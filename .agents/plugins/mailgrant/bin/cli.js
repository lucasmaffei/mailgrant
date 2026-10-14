#!/usr/bin/env node
// mailgrant MCP bridge. A thin stdio<->HTTP proxy: forwards MCP over stdio to a
// running mailgrant server's Streamable-HTTP endpoint (`$MAILGRANT_URL/mcp`),
// authenticating with the agent's `$MAILGRANT_TOKEN`.
//
// stdout IS the MCP protocol channel, so diagnostics go to stderr only — the
// sole output here is a fatal pre-launch console.error (user-facing CLI
// output). The token is passed to the proxy as an argv header, never logged.
import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

const MCP_PATH = "/mcp";

const base = process.env.MAILGRANT_URL;
const token = process.env.MAILGRANT_TOKEN;

if (!base || !token) {
  console.error(
    `[mailgrant-mcp] Missing ${!base ? "MAILGRANT_URL" : "MAILGRANT_TOKEN"}.

Point this bridge at your mailgrant server with this agent's token, e.g.:
  export MAILGRANT_URL=https://mail-mcp.example.com
  export MAILGRANT_TOKEN=...

mailgrant is self-hosted — see https://github.com/lucasmaffei/mailgrant`,
  );
  process.exit(1);
}

const url = `${base.replace(/\/+$/, "")}${MCP_PATH}`;
const proxyEntry = require.resolve("mcp-remote/dist/proxy.js");

const args = [
  proxyEntry,
  url,
  "--transport",
  "http-only",
  "--header",
  `Authorization: Bearer ${token}`,
  ...process.argv.slice(2),
];

const result = spawnSync(process.execPath, args, { stdio: "inherit" });
process.exit(result.status ?? 1);
