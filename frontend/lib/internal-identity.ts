import { createHmac, randomUUID } from "node:crypto";
import fs from "node:fs";

export type InternalIdentity = {
  v: 1;
  user_id: string;
  role: "admin" | "user";
  issued_at: number;
  request_id: string;
  method: string;
  path: string;
};

function secret(): string {
  const fileName = process.env.OOPSNOTE_BFF_HMAC_SECRET_FILE?.trim();
  if (fileName) {
    const value = fs.readFileSync(fileName, "utf8").trim();
    if (value) return value;
    throw new Error("OOPSNOTE_BFF_HMAC_SECRET_FILE points to an empty secret file");
  }
  const value = process.env.OOPSNOTE_BFF_HMAC_SECRET?.trim();
  if (value) return value;
  throw new Error("OOPSNOTE_BFF_HMAC_SECRET_FILE or OOPSNOTE_BFF_HMAC_SECRET must be configured");
}

export function signInternalIdentity(input: {
  userId: string;
  role: "admin" | "user";
  method: string;
  path: string;
  now?: number;
  requestId?: string;
}): { encoded: string; signature: string; identity: InternalIdentity } {
  const identity: InternalIdentity = {
    v: 1,
    user_id: input.userId,
    role: input.role,
    issued_at: input.now ?? Math.floor(Date.now() / 1000),
    request_id: input.requestId ?? randomUUID(),
    method: input.method.toUpperCase(),
    path: input.path,
  };
  const encoded = Buffer.from(JSON.stringify(identity), "utf8").toString("base64url");
  const signature = createHmac("sha256", secret()).update(encoded).digest("base64url");
  return { encoded, signature, identity };
}
