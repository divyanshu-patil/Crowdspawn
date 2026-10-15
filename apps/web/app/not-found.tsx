import Link from "next/link";
import { ErrorScreen } from "../components/ui";

export default function NotFound() {
  return (
    <ErrorScreen
      code="404"
      title="No spawn point here"
      message="This page doesn't exist. Start a plan or look at the sample."
      action={
        <>
          <Link className="btn" href="/plan/new">
            Start a plan
          </Link>
          <Link className="ghost" href="/sample">
            See the sample
          </Link>
        </>
      }
    />
  );
}
