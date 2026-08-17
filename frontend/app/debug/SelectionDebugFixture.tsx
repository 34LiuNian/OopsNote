"use client";

import { useRef, useState } from "react";
import { RotateCcw } from "lucide-react";
import { BatchSelectionOverlay } from "@/components/batch-continuous/BatchSelectionOverlay";
import { ImageSelectionStage, NormalizedRectEditor } from "@/components/image-selection";
import {
  buildPageMetrics,
  splitSelectionAcrossPages,
  type DocumentRect,
  type SelectionModel,
} from "@/components/batch-continuous";
import { Button, Heading, Text } from "@/components/ui/primitives";
import styles from "./SelectionDebugFixture.module.css";

const METRICS = buildPageMetrics(
  [{ id: "debug-page", pageIndex: 0, label: "选区样例", sourceWidth: 1000, sourceHeight: 650 }],
  { x: 0, y: 0, width: 1, height: 1 },
);

function selection(id: string, questionNo: number, rect: DocumentRect, status: SelectionModel["status"]): SelectionModel {
  return {
    id,
    questionNo,
    status,
    rect,
    start: { x: rect.left, y: rect.top },
    end: { x: rect.right, y: rect.bottom },
    slices: splitSelectionAcrossPages(rect, METRICS),
  };
}

function initialSelections() {
  return [
    selection("debug-pending", 1, { left: 45, top: 105, right: 590, bottom: 315 }, "pending"),
    selection("debug-completed", 2, { left: 625, top: 105, right: 950, bottom: 315 }, "completed"),
  ];
}

export function SelectionDebugFixture() {
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const [selections, setSelections] = useState<SelectionModel[]>(initialSelections);
  const [activeSelectionId, setActiveSelectionId] = useState<string | undefined>("debug-pending");
  const [crop, setCrop] = useState({ x: 0.12, y: 0.16, width: 0.76, height: 0.66 });

  const reset = () => {
    setSelections(initialSelections());
    setActiveSelectionId("debug-pending");
    setCrop({ x: 0.12, y: 0.16, width: 0.76, height: 0.66 });
  };

  return (
    <section id="selection-component-fixture" className={styles.root}>
      <div className={styles.header}>
        <div>
          <Heading as="h3" className={styles.title}>题目选区</Heading>
          <Text className={styles.subtitle}>BatchSelectionOverlay · pending / completed</Text>
        </div>
        <Button type="button" size="small" leadingVisual={RotateCcw} onClick={reset}>重置选区</Button>
      </div>

      <div ref={viewportRef} className={styles.viewport}>
        <div className={styles.stage} data-testid="selection-debug-stage">
          <div className={styles.paper} aria-hidden="true">
            <div className={styles.paperHeading}>空间向量与立体几何</div>
            <div className={`${styles.question} ${styles.questionOne}`}>
              <strong>1.</strong> 已知向量 a = (1, 2, -1)，b = (2, 0, 3)，求 a + b。
              <div className={styles.options}><span>A. (3, 2, 2)</span><span>B. (1, 2, 4)</span><span>C. (2, 2, 3)</span><span>D. (3, 0, 2)</span></div>
            </div>
            <div className={`${styles.question} ${styles.questionTwo}`}>
              <strong>2.</strong> 正方体 ABCD-A1B1C1D1 中，与 AB 垂直的棱共有多少条？
              <div className={styles.options}><span>A. 2</span><span>B. 4</span><span>C. 6</span><span>D. 8</span></div>
            </div>
            <div className={styles.divider} />
            <div className={`${styles.question} ${styles.questionThree}`}>
              <strong>3.</strong> 若平面 α 与平面 β 相交，则它们的交集是一条直线。
            </div>
          </div>

          <BatchSelectionOverlay
            metrics={METRICS}
            selections={selections}
            activeSelectionId={activeSelectionId}
            viewportRef={viewportRef}
            onActiveSelectionChange={setActiveSelectionId}
            onCreate={(created) => {
              setSelections((current) => {
                const questionNo = Math.max(0, ...current.map((item) => item.questionNo)) + 1;
                return [...current, { ...created, questionNo }];
              });
            }}
            onChange={(changed) => setSelections((current) => current.map((item) => item.id === changed.id ? changed : item))}
            onTooSmall={() => undefined}
          />
        </div>
      </div>

      <div className={styles.adapterGrid}>
        <div className={styles.adapterPanel}>
          <Text className={styles.adapterTitle}>页面 / 题图裁剪</Text>
          <Text className={styles.adapterHint}>NormalizedRectEditor · 同一 SelectionBox</Text>
          <ImageSelectionStage
            alt="页面裁剪示例"
            layout="fixed"
            fallback={<div className={styles.cropPaper}>页面 / 题图原图</div>}
            className={styles.cropStage}
          >
            <NormalizedRectEditor value={crop} onChange={setCrop} />
          </ImageSelectionStage>
        </div>
        <div className={styles.adapterNotes}>
          <Text className={styles.adapterTitle}>适配边界</Text>
          <Text className={styles.adapterHint}>框体、手柄、移动、缩放和最小尺寸由 SelectionBox 统一；裁剪只保存归一化矩形，批量扫描只负责文档坐标与题目状态。</Text>
        </div>
      </div>
    </section>
  );
}
