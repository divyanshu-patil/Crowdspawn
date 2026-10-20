import type { Metadata } from "next";
import type { TraceRow } from "@repo/contracts";
import trace from "../../../../public/sample-delhi-trace.json";
import { TraceView } from "../../../../components/TraceView";

export const metadata: Metadata = { title: "Sample Qloo trace: Delhi Gullies · Crowdspawn" };

export default function DelhiSampleTracePage() {
  return <TraceView id="sample-delhi" initial={trace as unknown as TraceRow[]} backHref="/sample/delhi" />;
}
