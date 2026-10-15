import type { Metadata } from "next";
import type { TraceRow } from "@repo/contracts";
import trace from "../../../public/sample-trace.json";
import { TraceView } from "../../../components/TraceView";

export const metadata: Metadata = { title: "Sample Qloo trace · Crowdspawn" };

export default function SampleTracePage() {
  return <TraceView id="sample" initial={trace as unknown as TraceRow[]} backHref="/sample" />;
}
