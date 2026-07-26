import { TOOL_SPECS } from "./oopsnote_tool_contracts.js";

let requestId = 0;
let connection = null;

async function getConnection(_pi) {
  if (connection) return connection;
  const url = _pi.getFlag("oopsnote-mcp-url");
  const token = _pi.getFlag("oopsnote-mcp-token");
  if (!url) throw new Error("OopsNote MCP URL is not configured");
  if (!token) throw new Error("OopsNote MCP token is not available to the extension");
  connection = { url: String(url), token: String(token) };
  return connection;
}

function parseSseJson(text, expectedId) {
  for (const line of String(text || "").split(/\r?\n/)) {
    if (!line.startsWith("data:")) continue;
    const message = JSON.parse(line.slice(5).trim());
    if (message.id === expectedId) return message;
  }
  throw new Error("OopsNote MCP returned no JSON-RPC result");
}

async function callMcp(pi, name, args) {
  const current = await getConnection(pi);
  const id = ++requestId;
  const response = await pi.http({
    url: current.url,
    method: "POST",
    headers: {
      Authorization: `Bearer ${current.token}`,
      Accept: "application/json, text/event-stream",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      jsonrpc: "2.0",
      id,
      method: "tools/call",
      params: { name, arguments: args || {} },
    }),
  });
  if (!response || response.status < 200 || response.status >= 300) {
    throw new Error(`OopsNote MCP HTTP failure: ${response?.status || 0}`);
  }
  const message = parseSseJson(response.body, id);
  if (message.error) throw new Error(message.error.message || "OopsNote MCP error");
  const result = message.result || {};
  if (result.isError) {
    const detail = (result.content || []).map((item) => item.text || "").join("\n");
    throw new Error(detail || `OopsNote MCP tool ${name} failed`);
  }
  return {
    content: Array.isArray(result.content) ? result.content : [],
    details: result.structuredContent || null,
  };
}

export default function oopsnoteMcpBridge(pi) {
  pi.registerFlag("oopsnote-mcp-url", {
    description: "Ephemeral loopback OopsNote MCP URL",
    type: "string",
  });
  pi.registerFlag("oopsnote-mcp-token", {
    description: "Ephemeral OopsNote MCP bearer token",
    type: "string",
  });

  for (const spec of TOOL_SPECS) {
    pi.registerTool({
      name: spec.name,
      label: spec.name === "ocr_image" ? "OCR image" : `OopsNote: ${spec.remoteName}`,
      description: spec.description,
      parameters: spec.parameters,
      async execute(_toolCallId, params) {
        return callMcp(pi, spec.remoteName, params);
      },
    });
  }

  pi.setActiveTools(TOOL_SPECS.map((spec) => spec.name));
  pi.on("session_start", async () => {
    connection = null;
  });
}
