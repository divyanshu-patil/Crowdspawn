import type { Metadata } from "next";
import { RegionScout } from "../../components/RegionScout";

export const metadata: Metadata = {
  title: "Region scout · Crowdspawn",
  description: "Pick any place on the map: see which genres and games its players love, and whether your game fits there.",
};

export default function ScoutPage() {
  return <RegionScout />;
}
