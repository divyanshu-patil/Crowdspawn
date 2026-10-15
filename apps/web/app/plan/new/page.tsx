import type { Metadata } from "next";
import { NewPlanForm } from "../../../components/NewPlanForm";

export const metadata: Metadata = { title: "New launch plan · Crowdspawn" };

export default function NewPlanPage() {
  return <NewPlanForm />;
}
