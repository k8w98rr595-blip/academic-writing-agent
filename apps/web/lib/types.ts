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
  estimate: number;
  uncertainty: { low: number; high: number };
  qualifyingWords: number;
  isMock: boolean;
  label: string;
  spans: EvidenceSpan[];
  providers: Array<{ name: string; modelVersion: string; estimate: number; isMock: boolean }>;
  qualityChecks?: {
    duplicateGroups: Array<{ count: number; occurrences: Array<{ paragraphId: string; start: number; end: number; preview: string }> }>;
    inlineCitationCount: number;
    referenceHeadingPresent: boolean;
    referenceEntryParagraphs: number;
    warnings: string[];
  };
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
