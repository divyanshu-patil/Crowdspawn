import type { Metadata } from "next";
import { TraceView } from "../../../../components/TraceView";

export const metadata: Metadata = { title: "Qloo call trace · Crowdspawn" };

export default async function TracePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <TraceView id={id} backHref={`/plan/${id}`} />;
}
