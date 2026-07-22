import { readFileSync } from "node:fs";
import { readFile, stat } from "node:fs/promises";
import { extname, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const MAX_BYTES = 12 * 1024 * 1024;
const MIME_TYPES = new Map([
  [".jpg", "image/jpeg"], [".jpeg", "image/jpeg"], [".png", "image/png"],
  [".webp", "image/webp"], [".gif", "image/gif"]
]);

function imageMime(path) {
  return MIME_TYPES.get(extname(path).toLowerCase());
}

function loadConfig() {
  const __dirname = dirname(fileURLToPath(import.meta.url));
  const configPath = resolve(__dirname, "..", "extensions.json");
  try {
    return JSON.parse(readFileSync(configPath, "utf-8"));
  } catch {
    return {};
  }
}

export default function (pi) {
  const cfg = loadConfig().ocr_image || {};
  const apiKey = cfg.dashscope_api_key;
  const model = cfg.model;

  pi.registerTool({
    name: "ocr_image",
    label: "OCR image",
    description: "Extract a single problem image into strict OCR JSON. Use only for OopsNote task assets.",
    parameters: {
      type: "object",
      properties: { path: { type: "string", description: "Absolute image asset path" } },
      required: ["path"],
      additionalProperties: false
    },
    async execute(_toolCallId, params) {
      const path = resolve(params.path);
      const mime = imageMime(path);
      if (!mime) throw new Error("Unsupported OCR image type");
      const info = await stat(path);
      if (info.size > MAX_BYTES) throw new Error("OCR image exceeds 12 MiB limit");
      if (!apiKey || !model) throw new Error("OCR configuration is required in .pi/extensions.json");
      const image = await readFile(path);
      const response = await fetch("https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions", {
        method: "POST",
        headers: { "Authorization": `Bearer ${apiKey}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          model,
          temperature: 0,
          messages: [{ role: "user", content: [
            { type: "image_url", image_url: { url: `data:${mime};base64,${image.toString("base64")}` } },
            { type: "text", text: "Extract only printed question content. Return one strict JSON object: {content_format:'oopsmark-v1', subject:'math|physics|chemistry', question_type:'单选题|多选题|填空题|解答题', problem_text:string, options:string[], has_diagram:boolean, uncertain_regions:string[], confidence:number}. Use OopsMark v1: inline math is $...$, display math is $$...$$, options never appear in problem_text, and never emit raw LaTex environments such as array, tabular, enumerate, or tikzpicture. Do not solve or invent unreadable text." }
          ] }],
          response_format: { type: "json_object" }
        })
      });
      if (!response.ok) {
        const errBody = await response.text().catch(() => "");
        throw new Error(`DashScope OCR failed: ${response.status} ${errBody.slice(0, 200)}`);
      }
      const body = await response.json();
      const content = body.choices?.[0]?.message?.content;
      if (typeof content !== "string") throw new Error("DashScope OCR returned no text content");
      const parsed = JSON.parse(content);
      return { content: [{ type: "text", text: JSON.stringify(parsed) }] };
    }
  });
}
