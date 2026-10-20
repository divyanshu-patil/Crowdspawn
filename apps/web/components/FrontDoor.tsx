"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { EXAMPLES } from "./LaunchAgent";

/** Landing input: the description goes to the launch agent, which runs at once (J16). */
export function FrontDoor() {
  const router = useRouter();
  const [goal, setGoal] = useState("");
  const ready = goal.trim().length >= 10;
  return (
    <form
      className="section stack front-door"
      onSubmit={(e) => {
        e.preventDefault();
        if (ready) router.push(`/agent?goal=${encodeURIComponent(goal.trim())}&run=1`);
      }}
    >
      <div className="field">
        <label className="label" htmlFor="front-goal">
          Describe your game and what you want to decide
        </label>
        <textarea
          id="front-goal"
          className="textarea"
          value={goal}
          maxLength={600}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="A cozy farming game for PC and Switch. Where should I launch first, and who should I partner with?"
        />
        <div className="row popular">
          <span className="label muted">Try</span>
          {EXAMPLES.map((x) => (
            <button key={x} type="button" className="chip-btn" onClick={() => setGoal(x)} title={x}>
              {x.split(".")[0]}
            </button>
          ))}
        </div>
      </div>
      <div className="row" style={{ alignItems: "center" }}>
        <button className="btn btn-lg" data-sfx="select" type="submit" disabled={!ready}>
          Plan my launch
        </button>
        <Link className="ghost" href="/sample">
          See a sample plan
        </Link>
        <Link className="textlink label" href="/plan/new">
          Advanced: pick comps yourself
        </Link>
      </div>
      <p className="hint">
        An agent picks comparable games, then ranks cities and partners with live Qloo data, showing every step.
      </p>
    </form>
  );
}
