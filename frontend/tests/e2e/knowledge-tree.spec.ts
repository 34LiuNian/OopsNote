import { expect, test, type Page } from "@playwright/test";
import type { KnowledgeTreeNode } from "../../types/api";
import {
  cascadeDisplayNodes,
  collectLeafIdSet,
  collectLeafTitles,
  compactSelectedNodeIds,
  filterTree,
  isTreeLeaf,
  selectedLeafIdsFromNodeIds,
} from "../../components/knowledge-tree/knowledgeTree";
import { waitForAppReady } from "./app-ready";

function node(partial: Partial<KnowledgeTreeNode> & Pick<KnowledgeTreeNode, "id" | "title" | "depth">): KnowledgeTreeNode {
  const children = partial.children ?? [];
  return {
    selectable: children.length === 0,
    is_leaf: children.length === 0,
    children,
    ...partial,
  };
}

const mathTree = node({
  id: "math-root",
  title: "数学",
  depth: 0,
  selectable: false,
  is_leaf: false,
  children: [
    node({
      id: "math-function",
      title: "函数与导数",
      depth: 1,
      selectable: false,
      is_leaf: false,
      children: [
        node({ id: "math-function-concept", title: "函数", depth: 2 }),
        node({ id: "math-derivative-concept", title: "导数的概念", depth: 2 }),
        node({ id: "math-derivative-calc", title: "导数的运算", depth: 2 }),
        node({ id: "math-derivative-app", title: "导数的应用", depth: 2 }),
        node({ id: "math-extreme", title: "极值与最值", depth: 2 }),
        node({ id: "math-inequality", title: "不等式", depth: 2 }),
        node({ id: "math-sequence", title: "数列", depth: 2 }),
      ],
    }),
  ],
});

test("leaf identity stays on the source tree after search prunes children", () => {
  const leafIds = collectLeafIdSet(mathTree);
  expect(leafIds.has("math-function")).toBe(false);
  expect(leafIds.has("math-function-concept")).toBe(true);

  const pruned = filterTree(mathTree, "函数与导数");
  const parent = pruned?.children[0];
  expect(parent?.id).toBe("math-function");
  expect(parent?.children).toEqual([]);
  expect(isTreeLeaf(parent!)).toBe(true);
  expect(leafIds.has(parent!.id)).toBe(false);
  expect(collectLeafTitles(mathTree.children[0])).toEqual([
    "函数",
    "导数的概念",
    "导数的运算",
    "导数的应用",
    "极值与最值",
    "不等式",
    "数列",
  ]);
  const selected = selectedLeafIdsFromNodeIds(mathTree, ["math-function"]);
  expect(selected.size).toBe(7);
  expect(compactSelectedNodeIds(mathTree, selected)).toEqual(["math-function"]);
  const functionLeaves = collectLeafIdSet(mathTree.children[0]);
  expect(cascadeDisplayNodes(mathTree, [...functionLeaves]).nodes.map((item) => item.id)).toEqual(["math-function"]);
  expect(cascadeDisplayNodes(mathTree, [...functionLeaves]).orphans).toEqual([]);
});

async function mockLibraryKnowledgeApis(page: Page, captured: { problemsUrl: string }) {
  await page.addInitScript(() => document.documentElement.classList.add("oops-splash-skip"));
  await page.route("**/api/auth/get-session*", async (route) => {
    await route.fulfill({
      json: {
        session: { id: "knowledge-tree-session", userId: "knowledge-tree-user" },
        user: { id: "knowledge-tree-user", name: "Knowledge Tree", email: "tree@example.test", role: "admin" },
      },
    });
  });
  await page.route("**/api/health", async (route) => {
    await route.fulfill({ json: { status: "ok" } });
  });
  await page.route(/\/api\/(?:backend\/)?settings\/tag-dimensions$/, async (route) => {
    await route.fulfill({ json: { dimensions: {} } });
  });
  await page.route(/\/api\/(?:backend\/)?tasks(?:\?.*)?$/, async (route) => {
    await route.fulfill({ json: { items: [] } });
  });
  await page.route(/\/api\/(?:backend\/)?tags\/tree/, async (route) => {
    await route.fulfill({
      json: {
        schema_version: "xkw-knowledge-tree-v1",
        subjects: {
          math: { subject: "math", subject_label: "数学", root: mathTree },
        },
      },
    });
  });
  await page.route(/\/api\/(?:backend\/)?tags(?:\?.*)?$/, async (route) => {
    await route.fulfill({ json: { items: [] } });
  });
  await page.route(/\/api\/(?:backend\/)?problems(?:\?.*)?$/, async (route) => {
    captured.problemsUrl = route.request().url();
    await route.fulfill({
      json: {
        items: [{
          task_id: "task-1",
          problem_id: "problem-1",
          question_no: "1",
          question_type: "解答题",
          content_format: "oopsmark-v1",
          problem_text: "第 1 道题",
          options: [],
          subject: "math",
          source: "questions.pdf",
          knowledge_points: ["函数"],
          knowledge_tags: ["函数"],
          error_tags: [],
          user_tags: [],
          created_at: "2026-07-21T10:00:00+08:00",
        }],
      },
    });
  });
}

test("library knowledge dialog can choose a subject then cascade-select a parent", async ({ page }) => {
  const captured = { problemsUrl: "" };
  await mockLibraryKnowledgeApis(page, captured);
  await page.goto("/library", { waitUntil: "domcontentloaded" });
  await waitForAppReady(page);

  await page.getByRole("button", { name: "选择知识点" }).click();
  const dialog = page.getByRole("dialog", { name: "选择知识点" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("选择学科后显示知识树")).toBeVisible();
  await dialog.getByRole("radio", { name: "数学" }).click();
  await expect(dialog.getByRole("checkbox", { name: "选择函数与导数", exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "完成" }).click();
  await expect(page.getByRole("complementary", { name: "题库筛选" }).getByRole("button", { name: "数学", exact: true })).toBeVisible();
});

test("library knowledge picker can cascade-select a parent and does not cap at six leaves", async ({ page }) => {
  const captured = { problemsUrl: "" };
  await mockLibraryKnowledgeApis(page, captured);
  await page.goto("/library", { waitUntil: "domcontentloaded" });
  await waitForAppReady(page);

  const sidebar = page.getByRole("complementary", { name: "题库筛选" });
  await sidebar.getByRole("button", { name: "全部", exact: true }).hover();
  await page.getByRole("radio", { name: "数学" }).click();
  await page.mouse.move(0, 0);
  await sidebar.getByRole("button", { name: "选择知识点" }).click();

  const dialog = page.getByRole("dialog", { name: "选择知识点" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("checkbox", { name: "选择函数与导数", exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "展开函数与导数" }).click();
  await expect(dialog.getByRole("checkbox", { name: "选择函数", exact: true })).toBeVisible();

  await dialog.getByRole("textbox", { name: "搜索知识点" }).fill("函数与导数");
  await dialog.getByRole("checkbox", { name: "选择函数与导数", exact: true }).check();
  await expect(dialog.getByRole("button", { name: "移除知识点 函数与导数", exact: true })).toBeVisible();
  await expect(page.getByText("知识点最多选择")).toHaveCount(0);

  await dialog.getByRole("textbox", { name: "搜索知识点" }).fill("");
  const expandParent = dialog.getByRole("button", { name: "展开函数与导数" });
  if (await expandParent.isVisible()) await expandParent.click();
  await expect(dialog.getByRole("checkbox", { name: "选择函数", exact: true })).toBeChecked();
  await expect(dialog.getByRole("checkbox", { name: "选择数列", exact: true })).toBeChecked();

  await dialog.getByRole("button", { name: "完成" }).click();
  await expect(dialog).toBeHidden();
  const sidebarChips = page.getByRole("complementary", { name: "题库筛选" }).getByRole("button", { name: /移除知识点 / });
  await expect(sidebarChips).toHaveCount(1);
  await expect(page.getByRole("complementary", { name: "题库筛选" }).getByRole("button", { name: "移除知识点 函数与导数", exact: true })).toBeVisible();

  await expect.poll(() => captured.problemsUrl).toContain("knowledge_node_id=math-function");
  const params = new URL(captured.problemsUrl).searchParams;
  expect(params.getAll("knowledge_node_id")).toEqual(["math-function"]);
  expect(params.getAll("knowledge_any")).toEqual([]);
});
