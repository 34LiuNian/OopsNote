declare module "react-katex" {
  import * as React from "react";

  export interface KaTeXProps {
    math: string;
    errorColor?: string;
    renderError?: (error: Error) => React.ReactNode;
  }

  export const BlockMath: React.ComponentType<KaTeXProps>;
  export const InlineMath: React.ComponentType<KaTeXProps>;
}
