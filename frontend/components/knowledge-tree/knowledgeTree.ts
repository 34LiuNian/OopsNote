import type { KnowledgeTreeNode } from "@/types/api";

export type NodeSelectionState = {
  checked: boolean;
  indeterminate: boolean;
};

export function isCoreNode(node: KnowledgeTreeNode): boolean {
  return !node.scope || node.scope === "core";
}

export function coreChildren(node: KnowledgeTreeNode): KnowledgeTreeNode[] {
  return node.children.filter(isCoreNode);
}

export function isTreeLeaf(node: KnowledgeTreeNode): boolean {
  return coreChildren(node).length === 0;
}

export function collectLeafIds(node: KnowledgeTreeNode): string[] {
  const children = coreChildren(node);
  if (!children.length) return [node.id];
  return children.flatMap(collectLeafIds);
}

export function collectExpandedIdsForSelection(
  root: KnowledgeTreeNode | null,
  selectedLeafIds: Set<string>,
): Set<string> {
  const expanded = new Set<string>();
  if (!root || selectedLeafIds.size === 0) return expanded;

  function visit(node: KnowledgeTreeNode): boolean {
    if (!isCoreNode(node)) return false;
    const selectedHere = isTreeLeaf(node) && selectedLeafIds.has(node.id);
    const selectedBelow = coreChildren(node).some(visit);
    if ((selectedHere || selectedBelow) && !isTreeLeaf(node)) expanded.add(node.id);
    return selectedHere || selectedBelow;
  }

  visit(root);
  return expanded;
}

export function findKnowledgeNode(node: KnowledgeTreeNode, id: string): KnowledgeTreeNode | null {
  if (node.id === id) return node;
  for (const child of node.children) {
    const match = findKnowledgeNode(child, id);
    if (match) return match;
  }
  return null;
}

export function filterTree(node: KnowledgeTreeNode, query: string): KnowledgeTreeNode | null {
  if (!isCoreNode(node)) return null;
  const children = node.children
    .map((child) => filterTree(child, query))
    .filter((child): child is KnowledgeTreeNode => child !== null);
  if (!query || node.title.toLocaleLowerCase().includes(query) || children.length) {
    return { ...node, children };
  }
  return null;
}

export function buildSelectionStates(
  node: KnowledgeTreeNode,
  selectedLeafIds: Set<string>,
  states: Map<string, NodeSelectionState>,
): { selected: number; total: number } {
  const children = coreChildren(node);
  if (!children.length) {
    const checked = selectedLeafIds.has(node.id);
    states.set(node.id, { checked, indeterminate: false });
    return { selected: checked ? 1 : 0, total: 1 };
  }

  const counts = children.reduce(
    (current, child) => {
      const childCounts = buildSelectionStates(child, selectedLeafIds, states);
      return {
        selected: current.selected + childCounts.selected,
        total: current.total + childCounts.total,
      };
    },
    { selected: 0, total: 0 },
  );
  states.set(node.id, {
    checked: counts.total > 0 && counts.selected === counts.total,
    indeterminate: counts.selected > 0 && counts.selected < counts.total,
  });
  return counts;
}

export function compactSelectedNodes(
  root: KnowledgeTreeNode | null,
  selectedLeafIds: Set<string>,
): KnowledgeTreeNode[] {
  if (!root) return [];

  function visit(node: KnowledgeTreeNode): KnowledgeTreeNode[] {
    const leafIds = collectLeafIds(node);
    if (leafIds.length && leafIds.every((id) => selectedLeafIds.has(id))) return [node];
    return coreChildren(node).flatMap(visit);
  }

  return coreChildren(root).flatMap(visit);
}

export function nodeTitlePath(root: KnowledgeTreeNode, id: string): string[] {
  const path: string[] = [];

  function visit(node: KnowledgeTreeNode, trail: string[]): boolean {
    const nextTrail = node.depth > 0 ? [...trail, node.title] : trail;
    if (node.id === id) {
      path.push(...nextTrail);
      return true;
    }
    return node.children.some((child) => visit(child, nextTrail));
  }

  visit(root, []);
  return path;
}

export function findLeavesByTitle(root: KnowledgeTreeNode, title: string): KnowledgeTreeNode[] {
  const needle = title.trim().toLocaleLowerCase();
  const matches: KnowledgeTreeNode[] = [];

  function visit(node: KnowledgeTreeNode) {
    if (isCoreNode(node) && isTreeLeaf(node) && node.title.trim().toLocaleLowerCase() === needle) {
      matches.push(node);
    }
    for (const child of node.children) visit(child);
  }

  visit(root);
  return matches;
}

export function selectedLeafIdsFromTitles(root: KnowledgeTreeNode | null, titles: string[]): Set<string> {
  const ids = new Set<string>();
  if (!root) return ids;
  for (const title of titles) {
    for (const leaf of findLeavesByTitle(root, title)) ids.add(leaf.id);
  }
  return ids;
}
