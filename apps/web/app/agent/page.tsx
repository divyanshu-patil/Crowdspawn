import type { Metadata } from "next";
import { LaunchAgent } from "../../components/LaunchAgent";

export const metadata: Metadata = {
  title: "Launch agent · Crowdspawn",
  description: "An agent that plans a game launch with Qloo tools, step by step, and shows its work.",
};

export default function AgentPage() {
  return <LaunchAgent />;
}
