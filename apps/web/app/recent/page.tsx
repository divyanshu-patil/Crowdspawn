import type { Metadata } from "next";
import { RecentPlans } from "../../components/RecentPlans";

export const metadata: Metadata = { title: "Recent launches · Crowdspawn" };

export default function RecentPage() {
  return <RecentPlans />;
}
