"use client";

import { useEffect, useState } from "react";
import { Activity, Gauge } from "lucide-react";
import { AccountSettingsNav } from "@/components/account/AccountSettingsNav";
import { PageHeader } from "@/components/layout/PageHeader";
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
  useEffect(() => {
    void fetch("/api/backend/me/quota", { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error("额度服务暂时不可用");
        const payload = await response.json() as { quota?: Quota } & Quota;
        setQuota(payload.quota || payload);
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : "无法读取额度"));
  }, []);

  const remaining = quota ? Math.max(0, quota.daily_success_limit - quota.used_units) : 0;
  return (
    <div className={styles.page}>
      <PageHeader title="个人账号" description="管理个人资料、账号安全和额度" />
      <AccountSettingsNav />
      <section className={styles.panel}>
        <div className={styles.panelHeading}><Gauge size={22} aria-hidden="true" /><div><h2>用量与额度</h2><p>额度按成功完成的 AI 任务计算，每日自动重置。</p></div></div>
        {error ? <p className={styles.state}>{error}</p> : quota ? (
          <div className={styles.usageGrid}>
            <div><span>今日剩余</span><strong>{remaining}</strong></div>
            <div><span>今日已用</span><strong>{quota.used_units}</strong></div>
            <div><span>每日额度</span><strong>{quota.daily_success_limit}</strong></div>
            <div><span><Activity size={14} aria-hidden="true" /> 当前并发</span><strong>{quota.active_runs} / {quota.max_concurrent_runs}</strong></div>
          </div>
        ) : <p className={styles.state}>正在读取额度...</p>}
      </section>
    </div>
  );
}
