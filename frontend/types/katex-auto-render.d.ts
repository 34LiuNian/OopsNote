declare module "katex/contrib/auto-render" {
  export default function renderMathInElement(
    element: HTMLElement,
    options?: {
      delimiters?: Array<{ left: string; right: string; display: boolean }>;
      ignoredTags?: string[];
      ignoredClasses?: string[];
      errorCallback?: (msg: string, err: unknown) => void;
      macros?: Record<string, string>;
      throwOnError?: boolean;
      strict?: boolean | "warn" | "ignore";
      trust?: boolean | ((context: unknown) => boolean);
      output?: "html" | "mathml" | "htmlAndMathml";
      preProcess?: (math: string) => string;
    },
  ): void;
}
