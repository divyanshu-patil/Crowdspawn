import type { Metadata } from "next";
import { LivePlan } from "../../../components/LivePlan";

export const metadata: Metadata = { title: "Launch plan · Crowdspawn" };

export default async function PlanPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <LivePlan id={id} />;
}
