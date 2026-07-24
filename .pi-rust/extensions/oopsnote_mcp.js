const PIPELINE_PREFIX = "mcp__oopsnote_pipeline_";

const TOOL_SPECS = [
  {
    name: "ocr_image",
    remoteName: "ocr_image",
    description: "Extract one OopsNote task image into strict OCR JSON.",
    parameters: {
      type: "object",
      properties: { path: { type: "string", description: "Absolute image asset path" } },
      required: ["path"],
      additionalProperties: false,
    },
  },
  {
    name: `${PIPELINE_PREFIX}get_task`,
    remoteName: "get_task",
    description: "Get one managed OopsNote task by id.",
    parameters: {
      type: "object",
      properties: { task_id: { type: "string" } },
      required: ["task_id"],
      additionalProperties: false,
    },
  },
  {
    name: `${PIPELINE_PREFIX}get_asset_path`,
    remoteName: "get_asset_path",
    description: "Resolve a managed OopsNote asset to an absolute local path.",
    parameters: {
      type: "object",
      properties: { asset_path: { type: "string" } },
      required: ["asset_path"],
      additionalProperties: false,
    },
  },
  {
    name: `${PIPELINE_PREFIX}list_tags`,
    remoteName: "list_tags",
    description: "List OopsNote tags, optionally filtered by dimension or query.",
    parameters: {
      type: "object",
      properties: {
        dimension: { type: ["string", "null"] },
        query: { type: ["string", "null"] },
        limit: { type: "integer", minimum: 1, maximum: 200 },
      },
      additionalProperties: false,
    },
  },
  {
    name: `${PIPELINE_PREFIX}create_tag`,
    remoteName: "create_tag",
    description: "Create or merge an OopsNote tag.",
    parameters: {
      type: "object",
      properties: {
        dimension: { type: "string", enum: ["knowledge", "error", "meta", "custom"] },
        value: { type: "string" },
        aliases: { type: ["array", "null"], items: { type: "string" } },
        subject: { type: ["string", "null"] },
      },
      required: ["dimension", "value"],
      additionalProperties: false,
    },
  },
  {
    name: `${PIPELINE_PREFIX}report_task_stage`,
    remoteName: "report_task_stage",
    description: "Report progress for the active managed OopsNote run.",
    parameters: {
      type: "object",
      properties: {
        task_id: { type: "string" },
        stage: { type: "string", enum: ["ocr", "solving", "verifying", "tagging", "finalizing", "syncing"] },
        run_id: { type: "string" },
        message: { type: ["string", "null"] },
      },
      required: ["task_id", "stage"],
      additionalProperties: false,
    },
  },
  {
    name: `${PIPELINE_PREFIX}finalize_task`,
    remoteName: "finalize_task",
    description: "Validate and atomically finalize the active OopsNote task.",
    parameters: {
      type: "object",
      properties: {
        task_id: { type: "string" },
        problem_json: { type: "string" },
        run_id: { type: "string" },
        sync_to_obsidian: { type: "boolean" },
        review_reason: { type: "string" },
      },
      required: ["task_id", "problem_json"],
      additionalProperties: false,
    },
  },
  {
    name: `${PIPELINE_PREFIX}fail_task`,
    remoteName: "fail_task",
    description: "Fail the active OopsNote task with an explicit reason.",
    parameters: {
      type: "object",
      properties: {
        task_id: { type: "string" },
        error: { type: "string" },
        run_id: { type: "string" },
        review_reason: { type: "string" },
      },
      required: ["task_id", "error"],
      additionalProperties: false,
    },
  },
];

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
