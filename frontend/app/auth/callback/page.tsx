"use client";

import { useEffect, useState } from "react";
import { AuthStatusScreen } from "@/components/providers";
import { completeSignin } from "@/lib/auth";

export default function AuthCallbackPage() {
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void completeSignin(window.location.href)
      .then((target) => window.location.replace(target))
      .catch((nextError: Error) => setError(nextError.message));
  }, []);

  return <AuthStatusScreen phase="callback" error={error} />;
}
