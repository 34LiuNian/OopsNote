/// <reference lib="webworker" />

import { Buffer } from "buffer";
import tex2svg from "isomorphic-tikzjax";

// The app tsconfig includes DOM types for React and Serwist worker typings;
// this file is loaded only as a dedicated worker, so bridge the two lib views
// at this execution boundary instead of weakening the project-wide types.
const context = self as unknown as DedicatedWorkerGlobalScope;
const TEX_RESOURCES = "/vendor/tikzjax/tex";
const browserTex2svg = tex2svg as unknown as (
  source: string,
  options: {
    texResourcesUrl: string;
    disableSanitize: boolean;
  },
) => Promise<string>;

if (!(globalThis as { Buffer?: typeof Buffer }).Buffer) {
  (globalThis as { Buffer?: typeof Buffer }).Buffer = Buffer;
}

context.onmessage = async (event: MessageEvent<{ source: string }>) => {
  try {
    const svg = await browserTex2svg(event.data.source, {
      texResourcesUrl: TEX_RESOURCES,
      // A Worker has no document. Sanitize the returned SVG on the main thread.
      disableSanitize: true,
    });
    context.postMessage({ svg });
  } catch (reason) {
    context.postMessage({ error: reason instanceof Error ? reason.message : "TikZJax 渲染失败" });
  }
};
