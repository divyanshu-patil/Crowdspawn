import type { Metadata } from "next";
import type { Plan } from "@repo/contracts";
import sample from "../../public/sample-plan.json";
import { PlanView } from "../../components/PlanView";
import { Notice } from "../../components/ui";
import { SampleCallout } from "../../components/Accuracy";
import Link from "next/link";

export const metadata: Metadata = { title: "Sample launch plan · Crowdspawn" };

export default function SamplePage() {
  return (
    <>
      <div style={{ paddingTop: 24 }}>
        <Notice>
          A saved plan from a real Qloo run. It loads without any API keys, so the numbers are a snapshot from the day it
          was recorded. Another example, a game set in Delhi, shows culture anchors at work:{" "}
          <Link className="textlink" href="/sample/delhi">
            Delhi Gullies
          </Link>
          .
        </Notice>
        <SampleCallout game={(sample as unknown as Plan).input.game.title} />
      </div>
      <PlanView plan={sample as unknown as Plan} traceHref="/sample/trace" />
    </>
  );
}
