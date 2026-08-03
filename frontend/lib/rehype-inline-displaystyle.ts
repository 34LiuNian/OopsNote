type HastNode = {
  type?: string;
  tagName?: string;
  properties?: { className?: unknown };
  children?: HastNode[];
  value?: string;
};

function hasClass(node: HastNode, expected: string) {
  const className = node.properties?.className;
  return Array.isArray(className) && className.includes(expected);
}

/** Keep inline math inline while using display-style TeX at the OopsMark web boundary. */
export function rehypeInlineDisplaystyle() {
  return (tree: HastNode) => {
    const visit = (node: HastNode) => {
      if (node.type === "element" && node.tagName === "code" && hasClass(node, "math-inline")) {
        for (const child of node.children ?? []) {
          if (child.type === "text" && child.value && !child.value.trimStart().startsWith("\\displaystyle")) {
            child.value = `\\displaystyle ${child.value}`;
          }
        }
      }
      for (const child of node.children ?? []) visit(child);
    };
    visit(tree);
  };
}
