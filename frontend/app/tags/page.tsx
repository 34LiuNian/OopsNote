"use client";

import { Box, Button, Flash, FormControl, Heading, Label, Select, Spinner, Text, TextInput } from "@primer/react";
import { useCallback, useEffect, useState } from "react";
import { createTag, searchTags } from "../../features/tags/api";
import { TAG_DIMENSIONS, useTagDimensions } from "../../features/tags";
import type {
  TagDimension,
  TagItem,
} from "../../types/api";

const LABEL_VARIANTS = [
  "secondary",
  "accent",
  "success",
  "attention",
  "danger",
  "done",
];

export default function TagsPage() {
  const {
    setDimensions: setDims,
    effectiveDimensions: effectiveDims,
    isLoading: isLoadingDims,
    error: dimsError,
    save: saveDims,
  } = useTagDimensions();

  const [dimFilter, setDimFilter] = useState<TagDimension | "">("");
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<TagItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>("");
  const [ok, setOk] = useState<string>("");

  const [newDim, setNewDim] = useState<TagDimension>("knowledge");
  const [newValue, setNewValue] = useState("");
  const [newAliases, setNewAliases] = useState("");

  const loadTags = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await searchTags({
        dimension: dimFilter || undefined,
        query: query.trim() || undefined,
        limit: 100,
      });
      setItems(Array.isArray(data.items) ? data.items : []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载标签失败");
    } finally {
      setLoading(false);
    }
  }, [dimFilter, query]);

  useEffect(() => {
    loadTags();
  }, [loadTags]);

  const onCreate = async () => {
    setOk("");
    setError("");
    const value = newValue.trim();
    if (!value) {
      setError("请输入标签内容");
      return;
    }
    const aliases = newAliases
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    try {
      await createTag({ dimension: newDim, value, aliases });
      setNewValue("");
      setNewAliases("");
      setOk("已保存");
      await loadTags();
    } catch (e) {
      setError(e instanceof Error ? e.message : "创建标签失败");
    }
  };

  const onSaveDims = async () => {
    setOk("");
    setError("");
    try {
      await saveDims();
      setOk("已保存配置");
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存配置失败");
    }
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <Box sx={{ p: 3, border: "1px solid", borderColor: "border.default", borderRadius: 2 }}>
        <Box sx={{ mb: 3 }}>
          <Text sx={{ fontSize: 0, color: "fg.muted", textTransform: "uppercase" }}>Tags</Text>
          <Heading as="h2" sx={{ fontSize: 3 }}>
            标签管理
          </Heading>
        </Box>

        {dimsError ? (
          <Flash variant="danger" sx={{ mb: 3 }}>
            {dimsError}
          </Flash>
        ) : null}

        {error ? (
          <Flash variant="danger" sx={{ mb: 3 }}>
            {error}
          </Flash>
        ) : null}
        {ok ? (
          <Flash variant="success" sx={{ mb: 3 }}>
            {ok}
          </Flash>
        ) : null}

        <Box sx={{ display: "grid", gridTemplateColumns: ["1fr", "1fr 1fr"], gap: 3 }}>
          <FormControl>
            <FormControl.Label>维度</FormControl.Label>
            <Select value={dimFilter} onChange={(e) => setDimFilter(e.target.value as TagDimension | "")} block>
              <Select.Option value="">全部</Select.Option>
              {TAG_DIMENSIONS.map((d) => (
                <Select.Option key={d.key} value={d.key}>
                  {effectiveDims[d.key]?.label || d.fallbackLabel}
                </Select.Option>
              ))}
            </Select>
          </FormControl>
          <FormControl>
            <FormControl.Label>搜索</FormControl.Label>
            <TextInput value={query} onChange={(e) => setQuery(e.target.value)} placeholder="输入几个字模糊搜索" block />
          </FormControl>
        </Box>

        <Box sx={{ mt: 3, display: "flex", alignItems: "center", gap: 2 }}>
          <Button onClick={() => loadTags()} disabled={loading}>
            {loading ? (
              <>
                <Spinner size="small" sx={{ mr: 1 }} />
                加载中…
              </>
            ) : (
              "刷新"
            )}
          </Button>
          <Text sx={{ color: "fg.muted", fontSize: 1 }}>共 {items.length} 条</Text>
        </Box>

        <Box sx={{ mt: 3, display: "flex", flexWrap: "wrap", gap: 2 }}>
          {items.length === 0 ? (
            <Text sx={{ color: "fg.muted" }}>暂无标签</Text>
          ) : (
            items.map((t) => (
              <Label key={t.id} variant={(effectiveDims[t.dimension]?.label_variant || "secondary") as any}>
                {t.value}
              </Label>
            ))
          )}
        </Box>
      </Box>

      <Box sx={{ p: 3, border: "1px solid", borderColor: "border.default", borderRadius: 2 }}>
        <Heading as="h3" sx={{ fontSize: 2, mb: 2 }}>
          新增标签
        </Heading>
        <Box sx={{ display: "grid", gridTemplateColumns: ["1fr", "220px 1fr"], gap: 3 }}>
          <FormControl>
            <FormControl.Label>维度</FormControl.Label>
            <Select value={newDim} onChange={(e) => setNewDim(e.target.value as TagDimension)} block>
              {TAG_DIMENSIONS.map((d) => (
                <Select.Option key={d.key} value={d.key}>
                  {effectiveDims[d.key]?.label || d.fallbackLabel}
                </Select.Option>
              ))}
            </Select>
          </FormControl>
          <FormControl>
            <FormControl.Label>标签内容</FormControl.Label>
            <TextInput value={newValue} onChange={(e) => setNewValue(e.target.value)} placeholder="例如：数学/函数/单调性" block />
          </FormControl>
        </Box>

        <Box sx={{ mt: 3 }}>
          <FormControl>
            <FormControl.Label>别名（可选，逗号分隔）</FormControl.Label>
            <TextInput value={newAliases} onChange={(e) => setNewAliases(e.target.value)} placeholder="同义词1, 同义词2" block />
          </FormControl>
        </Box>

        <Box sx={{ mt: 3, display: "flex", gap: 2 }}>
          <Button variant="primary" onClick={onCreate}>
            保存
          </Button>
        </Box>
      </Box>

      <Box sx={{ p: 3, border: "1px solid", borderColor: "border.default", borderRadius: 2 }}>
        <Heading as="h3" sx={{ fontSize: 2, mb: 2 }}>
          维度样式（颜色）
        </Heading>
        <Text sx={{ color: "fg.muted", fontSize: 1, mb: 3, display: "block" }}>
          这里配置每个维度使用的 Label 颜色（Primer variant）。
        </Text>

        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: ["1fr", "160px 1fr 220px 120px"],
            gap: 3,
            alignItems: "end",
          }}
        >
          <Text sx={{ fontWeight: "bold" }}>维度</Text>
          <Text sx={{ fontWeight: "bold" }}>显示名称</Text>
          <Text sx={{ fontWeight: "bold" }}>颜色</Text>
          <Box />

          {TAG_DIMENSIONS.map((d) => (
            <Box key={d.key} sx={{ display: "contents" }}>
              <Text>{d.key}</Text>
              <TextInput
                value={effectiveDims[d.key]?.label || d.fallbackLabel}
                onChange={(e) => {
                  setDims((prev) => ({
                    ...prev,
                    [d.key]: {
                      label: e.target.value,
                      label_variant: prev[d.key]?.label_variant || "secondary",
                    },
                  }));
                }}
                block
              />
              <Select
                value={effectiveDims[d.key]?.label_variant || "secondary"}
                onChange={(e) => {
                  setDims((prev) => ({
                    ...prev,
                    [d.key]: {
                      label: prev[d.key]?.label || d.fallbackLabel,
                      label_variant: e.target.value,
                    },
                  }));
                }}
                block
              >
                {LABEL_VARIANTS.map((v) => (
                  <Select.Option key={v} value={v}>
                    {v}
                  </Select.Option>
                ))}
              </Select>
              <Label variant={(effectiveDims[d.key]?.label_variant || "secondary") as any}>
                预览
              </Label>
            </Box>
          ))}
        </Box>

        <Box sx={{ mt: 3, display: "flex", gap: 2 }}>
          <Button variant="primary" onClick={onSaveDims} disabled={isLoadingDims}>
            {isLoadingDims ? (
              <>
                <Spinner size="small" sx={{ mr: 1 }} />
                保存中…
              </>
            ) : (
              "保存配置"
            )}
          </Button>
        </Box>
      </Box>
    </Box>
  );
}
