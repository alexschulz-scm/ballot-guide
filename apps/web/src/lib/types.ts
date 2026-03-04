// ---------------------------------------------------------------------------
// Primitive shared types
// ---------------------------------------------------------------------------

export interface SourceCitation {
  name: string;
  url: string;
  bias_rating: string | null;
  fetched_at: string; // ISO 8601
}

export interface ElectionSummary {
  id: string; // "FL-2026-GEN"
  name: string; // "2026 Florida General Election"
  date: string; // "2026-11-03"
  state: string; // "FL"
}

export interface PrecinctInfo {
  county: string;
  district: string | null;
  precinct_id: string | null;
}

// ---------------------------------------------------------------------------
// Stage output types
// ---------------------------------------------------------------------------

export interface CandidateAnalysis {
  candidate_id: string;
  name: string;
  party: string | null;
  bio_summary: string | null;
  positions: Record<string, string>; // topic_key → 1-sentence summary
  top_donors: string[]; // max 3, formatted "Name ($Amount)"
  funding_total: string | null;
  sources: SourceCitation[];
}

export interface MeasureAnalysis {
  measure_id: string;
  short_title: string;
  plain_english_summary: string;
  what_yes_means: string;
  what_no_means: string;
  fiscal_impact: string | null;
  fiscal_impact_source: string | null;
  proponent_argument: string;
  opponent_argument: string;
  proponent_source: string;
  opponent_source: string;
  topic_tags: string[];
  data_completeness: "full" | "partial" | "limited";
  sources: SourceCitation[];
}

export interface RaceAnalysis {
  race_id: string;
  race_title: string;
  race_type: string;
  candidates: CandidateAnalysis[];
  data_completeness: "full" | "partial" | "limited";
  sources: SourceCitation[];
}

export interface BallotReportItem {
  item_type: "measure" | "race";
  relevance_score: number;
  relevance_reason: string;
  matched_priorities: string[];
  measure?: MeasureAnalysis;
  race?: RaceAnalysis;
}

export interface BallotReport {
  session_id: string;
  generated_at: string; // ISO 8601
  election: ElectionSummary;
  precinct: PrecinctInfo;
  user_priorities: string[];
  items: BallotReportItem[];
}

// ---------------------------------------------------------------------------
// SSE event types (discriminated union on event_type)
// ---------------------------------------------------------------------------

export interface IntakeCompleteEvent {
  event_type: "intake_complete";
  session_id: string;
  timestamp: string;
  zip_code: string;
  priorities: string[];
  display_name: string | null;
}

export interface ClarificationNeededEvent {
  event_type: "clarification_needed";
  session_id: string;
  timestamp: string;
  question: string;
}

export interface BallotFoundEvent {
  event_type: "ballot_found";
  session_id: string;
  timestamp: string;
  election_name: string;
  item_count: number;
  message: string;
}

export interface ItemAnalyzedEvent {
  event_type: "item_analyzed";
  session_id: string;
  timestamp: string;
  item_id: string;
  item_title: string;
  items_complete: number;
  items_total: number;
}

export interface RankingCompleteEvent {
  event_type: "ranking_complete";
  session_id: string;
  timestamp: string;
  top_item_title: string;
}

export interface ReportCompleteEvent {
  event_type: "report_complete";
  session_id: string;
  timestamp: string;
  report: BallotReport;
}

export interface ErrorEvent {
  event_type: "error";
  session_id: string;
  timestamp: string;
  error_code: string;
  message: string;
  recoverable: boolean;
}

export interface DoneEvent {
  event_type: "done";
  session_id: string;
  timestamp: string; // ISO 8601 — Integration Review Issue 6
}

export type OrchestratorEvent =
  | IntakeCompleteEvent
  | ClarificationNeededEvent
  | BallotFoundEvent
  | ItemAnalyzedEvent
  | RankingCompleteEvent
  | ReportCompleteEvent
  | ErrorEvent
  | DoneEvent;

// ---------------------------------------------------------------------------
// Session / API types
// ---------------------------------------------------------------------------

export interface ElectionListItem {
  id: string;
  name: string;
  election_date: string;
  is_historical: boolean;
}

export interface SessionMetadata {
  session_id: string;
  created_at: string;
  updated_at: string;
  display_name: string | null;
  language: string;
  status: "active" | "processing" | "error";
  zip_code: string | null;
  priorities: string[];
  has_report: boolean;
  election_name: string | null;
  election_id: string | null;
  message_count: number;
}

export interface ReportResponse {
  session_id: string;
  report: BallotReport;
  generated_at: string;
  data_freshness: "fresh" | "stale" | "very_stale";
  display_name: string | null;
  priorities: string[];
}

export interface APIError {
  error_code: string;
  message: string;
  detail?: string;
}
