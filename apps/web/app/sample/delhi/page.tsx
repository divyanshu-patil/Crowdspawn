import type { Metadata } from "next";
import type { Plan } from "@repo/contracts";
import sample from "../../../public/sample-delhi-plan.json";
import { PlanView } from "../../../components/PlanView";
import { Notice } from "../../../components/ui";

export const metadata: Metadata = { title: "Sample plan: Delhi Gullies · Crowdspawn" };

export default function DelhiSamplePage() {
  return (
    <>
      <div style={{ paddingTop: 24 }}>
        <Notice>
          A saved plan from a real Qloo run, for a game set in Delhi. Its culture anchors (films, shows and music from
          the setting) lift Indian cities. Saved before partner lift and launch actions existed, so those parts show less.
        </Notice>
      </div>
      <PlanView plan={sample as unknown as Plan} traceHref="/sample/delhi/trace" />
    </>
  );
}
