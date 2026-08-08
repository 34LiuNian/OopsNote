import { toNextJsHandler } from "better-auth/next-js";
import { auth } from "@/lib/better-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export const { GET, POST, PATCH, PUT, DELETE } = toNextJsHandler(auth);
