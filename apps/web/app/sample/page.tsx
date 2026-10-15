import type { Metadata } from "next";
import type { Plan } from "@repo/contracts";
import sample from "../../public/sample-plan.json";
import { PlanView } from "../../components/PlanView";
import { Notice } from "../../components/ui";

export const metadata: Metadata = { title: "Sample launch plan · Crowdspawn" };

export default function SamplePage() {
  return (
    <>
      <div style={{ paddingTop: 24 }}>
        <Notice>
          A saved plan from a real Qloo run. It loads without any API keys, so the numbers are a snapshot from the day it
          was recorded.
        </Notice>
      </div>
      <PlanView plan={sample as unknown as Plan} traceHref="/sample/trace" />
    </>
  );
}
