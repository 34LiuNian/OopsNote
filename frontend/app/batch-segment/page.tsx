import { Suspense } from "react";
import { BatchScanForm } from "../../features/upload";

export default function BatchSegmentPage() {
  return <Suspense fallback={null}><BatchScanForm /></Suspense>;
}
