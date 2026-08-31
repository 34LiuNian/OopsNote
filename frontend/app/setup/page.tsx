import { redirect } from "next/navigation";
import { betterAuthIdentityStats } from "@/lib/better-auth-database";
import { bootstrapSecret } from "@/lib/better-auth-bootstrap";
import { SetupForm } from "./SetupForm";

export const dynamic = "force-dynamic";

/**
 * 首次启动引导页：bootstrap 密钥已挂载且尚未创建任何用户时可达；
 * 否则直接回到登录页。创建完成后自动关闭。
 */
export default function SetupPage() {
  if (!bootstrapSecret() || betterAuthIdentityStats().totalUsers !== 0) {
    redirect("/login");
  }
  return <SetupForm />;
}
