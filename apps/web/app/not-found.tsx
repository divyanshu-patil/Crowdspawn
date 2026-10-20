import Link from "next/link";
import { ErrorScreen } from "../components/ui";

export default function NotFound() {
  return (
    <ErrorScreen
      code="404"
      title="No spawn point here"
      message="This page doesn't exist. Plan a launch or look at the sample."
      action={
        <>
          <Link className="btn" href="/agent">
            Plan my launch
          </Link>
          <Link className="ghost" href="/sample">
            See the sample
          </Link>
        </>
      }
    />
  );
}
