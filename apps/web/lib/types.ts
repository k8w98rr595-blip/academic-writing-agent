export type Paragraph = { id: string; text: string };

export type EvidenceSpan = {
  paragraphId: string;
  start: number;
  end: number;
  score: number;
  evidence: "consensus" | "single";
  providers: string[];
};

export type DetectionResult = {
  overallScore: number | null;
  estimate: number | null;
  confidence: number | null;
  uncertainty: { low: number | null; high: number | null };
  qualifyingWords: number;
  isMock: boolean;
  label: string;
  fusionStatus: "provider-agreement" | "single-provider" | "disagreement" | "partial" | "unavailable";
  disagreement: boolean;
  fusionRule: string;
  spans: EvidenceSpan[];
  providers: Array<{
    overallScore: number | null;
    sentenceSpans: Array<{ paragraphId: string; start: number; end: number; score: number; confidence: number | null }>;
    confidence: number | null;
    provider: string;
    providerModelVersion: string | null;
    requestId: string | null;
    warnings: string[];
    isMock: boolean;
    latencyMs: number;
    status: "success" | "failed";
    error: null | { code: string; message: string; retryable: boolean };
    name: string;
    modelVersion: string | null;
    estimate: number | null;
  }>;
  warnings: string[];
  disclaimer: string;
};

export type Patch = {
  id: string;
  baseVersionId: string;
  paragraphId: string;
  originalText: string;
  revisedText: string;
  reason: string;
  protectedStatus: string;
  status: "pending" | "accepted" | "rejected";
  isMock?: boolean;
  provider?: string;
  modelVersion?: string;
  validatorModelVersion?: string | null;
  createdAt?: string;
};

export type VersionSummary = {
  id: string;
  number: number;
  wordCount: number;
  source: string;
  createdAt: string;
};

export type PaperDocument = {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  expiresAt: string;
  currentVersion: VersionSummary & { paragraphs: Paragraph[] };
  versions: VersionSummary[];
  analysis: null | {
    id: string;
    versionId: string;
    status: string;
    isStale: boolean;
    result: DetectionResult | null;
    createdAt: string;
    completedAt: string | null;
  };
  patches: Patch[];
};

export type DocumentListItem = { id: string; title: string; updatedAt: string; expiresAt: string };

declare global {
  interface Window {
    PAPERLIGHT_CONFIG?: { apiBaseUrl: string; basePath: string };
  }
}
