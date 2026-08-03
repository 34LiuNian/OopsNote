"use client";

import { Cpu } from "lucide-react";
import { Box, Button, FormControl, Heading, Spinner, Text, TextInput } from "@/components/ui/primitives";

type Props = {
  value: string;
  current: number | null;
  isLoading: boolean;
  isSaving: boolean;
  isDirty: boolean;
  message: string;
  onChange: (value: string) => void;
  onReset: () => void;
  onSave: () => void;
};

export function SettingsRuntimeSection(props: Props) {
  return (
    <Box className="oops-card" sx={{ p: 3 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 3, mb: 3, flexWrap: "wrap" }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
          <Cpu size={16} />
          <Box><Text className="oops-section-subtitle">AI Runtime</Text><Heading as="h3" className="oops-section-title" sx={{ m: 0, fontSize: 2 }}>LangChain 并发任务</Heading></Box>
        </Box>
        <Box sx={{ display: "flex", gap: 2 }}><Button onClick={props.onReset} disabled={!props.isDirty || props.isSaving}>重置</Button><Button variant="primary" onClick={props.onSave} disabled={!props.isDirty || props.isSaving}>保存</Button></Box>
      </Box>
      {props.isLoading ? <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}><Spinner size="medium" /></Box> : (
        <FormControl>
          <FormControl.Label>最大并发数</FormControl.Label>
          <TextInput type="number" min={1} max={16} step={1} value={props.value} onChange={(event) => props.onChange(event.target.value)} block monospace />
          <FormControl.Caption>范围 1–16；当前配置 {props.current ?? "-"}，保存后重启 OopsNote 生效</FormControl.Caption>
        </FormControl>
      )}
      {props.message && <Text role="status" sx={{ mt: 3, color: /失败|整数/.test(props.message) ? "fg.danger" : "fg.success", fontSize: 1 }}>{props.message}</Text>}
    </Box>
  );
}
