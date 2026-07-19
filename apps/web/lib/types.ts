export type Paragraph = { id: string; text: string };

export type EvidenceSpan = {
  paragraphId: string;
  start: number;
  end: number;
  classification: "ai_generated" | "ai_assisted";
  score: number;
  confidence: number;
};

export type PangramDetectionResult = {
  provider: "Pangram" | "Mock Pangram";
  providerModelVersion: string | null;
  isMock: boolean;
  status: "success" | "failed";
  error: null | { code: string; message: string; retryable: boolean };
  prediction: string | null;
  qualifyingWords: number;
  aiGeneratedPercent: number | null;
  aiAssistedPercent: number | null;
  humanPercent: number | null;
  combinedRiskPercent: number | null;
  spans: EvidenceSpan[];
  requestId: string | null;
  warnings: string[];
  disclaimer: string;
  analyzedVersionId: string;
  analyzedAt: string;
  latencyMs: number;
  riskComparison?: {
    beforePercent: number;
    afterPercent: number;
    changePercentagePoints: number;
    beforeAnalysisId: string;
  };
};

export type LegacyDetectionResult = {
  isMock: boolean;
  estimate?: number | null;
  label?: string;
  spans?: unknown[];
  warnings?: string[];
  disclaimer?: string;
};

export type DetectionResult = PangramDetectionResult | LegacyDetectionResult;

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
