"use client";

import { useCallback, useEffect, useState } from "react";
import { Activity, Gauge, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/primitives";
import { AccountSettingsNav } from "@/components/account/AccountSettingsNav";
import { PageHeader } from "@/components/layout/PageHeader";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { notifyRequestError } from "@/lib/requestError";
import styles from "../account.module.css";

type Quota = {
  daily_success_limit: number;
  used_units: number;
  active_runs: number;
  max_concurrent_runs: number;
};

export default function AccountUsagePage() {
  const [quota, setQuota] = useState<Quota | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/api/backend/me/quota", { cache: "no-store" });
      if (!response.ok) throw new Error("额度服务暂时不可用");
      const payload = await response.json() as { quota?: Quota } & Quota;
      setQuota(payload.quota || payload);
    } catch (reason) {
      setError(notifyRequestError("加载额度失败", reason, "无法读取额度"));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    const timer = setTimeout(() => {
      void load();
    }, 0);
    return () => clearTimeout(timer);
  }, [load]);

  const remaining = quota ? Math.max(0, quota.daily_success_limit - quota.used_units) : 0;
  return (
    <div className={styles.page}>
      <PageHeader title="个人账号" description="管理个人资料、账号安全和额度" />
      <AccountSettingsNav />
      <section className={styles.panel}>
        <div className={styles.panelHeading}><Gauge size={22} aria-hidden="true" /><div><h2>用量与额度</h2><p>额度按成功完成的 AI 任务计算，每日自动重置。</p></div></div>
        <ErrorBanner message={error} title="加载额度失败" />
        {error ? <div className={styles.state}><p>额度信息暂时不可用。</p><Button variant="secondary" size="small" leadingVisual={RefreshCw} onClick={() => void load()}>重新加载</Button></div> : quota ? (
          <div className={styles.usageGrid}>
            <div><span>今日剩余</span><strong>{remaining}</strong></div>
            <div><span>今日已用</span><strong>{quota.used_units}</strong></div>
            <div><span>每日额度</span><strong>{quota.daily_success_limit}</strong></div>
            <div><span><Activity size={14} aria-hidden="true" /> 当前并发</span><strong>{quota.active_runs} / {quota.max_concurrent_runs}</strong></div>
          </div>
        ) : <p className={styles.state}>{loading ? "正在读取额度..." : "额度信息暂时不可用。"}</p>}
      </section>
    </div>
  );
}
