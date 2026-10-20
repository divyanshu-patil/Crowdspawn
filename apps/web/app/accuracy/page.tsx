import type { Metadata } from "next";
import { AccuracyReport } from "../../components/Accuracy";

export const metadata: Metadata = {
  title: "How accurate is it? · Crowdspawn",
  description: "Crowdspawn's city ranking against Google Trends, an LLM without Qloo data, and plain popularity.",
};

export default function AccuracyPage() {
  return <AccuracyReport />;
}
