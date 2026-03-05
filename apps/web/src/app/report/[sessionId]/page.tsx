import type { Metadata } from "next";
import ReportView from "@/components/report/ReportView";

export const metadata: Metadata = {
  title: "Ballot Guide — Florida Voter Guide",
  description: "A personalized, factual, source-cited Florida ballot guide.",
  openGraph: {
    title: "Ballot Guide — Florida Voter Guide",
    description: "Understand your Florida ballot in plain language.",
    type: "article",
  },
};

export default async function ReportPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = await params;
  return <ReportView sessionId={sessionId} />;
}
