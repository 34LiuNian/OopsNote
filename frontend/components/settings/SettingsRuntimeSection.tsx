"use client";

import { Cpu } from "lucide-react";
import { Box, Button, FormControl, Heading, Spinner, Text, TextInput } from "@/components/ui/primitives";
import sxStyles from "./SettingsRuntimeSection.sx.module.css";

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
    <Box className={["oops-card", sxStyles.sx1].filter(Boolean).join(" ")} >
      <Box className={sxStyles.sx2}>
        <Box className={sxStyles.sx3}>
          <Cpu size={16} />
          <Box><Text className="oops-section-subtitle">AI Runtime</Text><Heading as="h3" className={["oops-section-title", sxStyles.sx4].filter(Boolean).join(" ")} >LangChain 并发任务</Heading></Box>
        </Box>
        <Box className={sxStyles.sx5}><Button onClick={props.onReset} disabled={!props.isDirty || props.isSaving}>重置</Button><Button variant="primary" onClick={props.onSave} disabled={!props.isDirty || props.isSaving}>保存</Button></Box>
      </Box>
      {props.isLoading ? <Box className={sxStyles.sx6}><Spinner size="medium" /></Box> : (
        <FormControl>
          <FormControl.Label>最大并发数</FormControl.Label>
          <TextInput type="number" min={1} max={16} step={1} value={props.value} onChange={(event) => props.onChange(event.target.value)} block monospace />
          <FormControl.Caption>范围 1–16；当前配置 {props.current ?? "-"}，保存后重启 OopsNote 生效</FormControl.Caption>
        </FormControl>
      )}
      {props.message && <Text role="status" className={sxStyles.message} data-status={/失败|错误|error|unavailable|invalid|整数/i.test(props.message) ? "danger" : "success"}>{props.message}</Text>}
    </Box>
  );
}
