"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { onServerState, type ServerState } from "../lib/api";
import { Notice } from "./ui";

/** Tells visitors a sleeping API host is waking up, and gives them a way out if it never answers. */
export function ServerStatus() {
  const [state, setState] = useState<ServerState>("ok");
  useEffect(() => {
    const off = onServerState(setState);
    return () => void off();
  }, []);
  if (state === "ok") return null;
  return (
    <div className="server-status">
      {state === "waking" ? (
        <Notice>Starting the server, this can take up to a minute…</Notice>
      ) : (
        <Notice tone="warn">
          <span>Can&apos;t reach the server right now. </span>
          <span className="row" style={{ marginTop: 8 }}>
            <button className="btn" onClick={() => location.reload()}>
              Retry
            </button>
            <Link className="ghost" href="/sample">
              See the sample plan
            </Link>
          </span>
        </Notice>
      )}
    </div>
  );
}
