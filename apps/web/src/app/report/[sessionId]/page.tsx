import ReportView from "@/components/report/ReportView";

export default async function ReportPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = await params;
  return <ReportView sessionId={sessionId} />;
}
