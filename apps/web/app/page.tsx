"use client";

import { useCallback, useEffect, useState } from "react";
import { api, clearSession, fetchDocument, sessionToken, storeSession } from "@/lib/api";
import type { DocumentListItem, PaperDocument } from "@/lib/types";
import { CreateDocument } from "@/components/CreateDocument";
import { LoginScreen } from "@/components/LoginScreen";
import { Workspace } from "@/components/Workspace";

export default function HomePage() {
  const [authenticated, setAuthenticated] = useState(false);
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [activeDocument, setActiveDocument] = useState<PaperDocument | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refreshList = useCallback(async (preferredId?: string) => {
    const payload = await api<{ documents: DocumentListItem[] }>("/api/v1/documents");
    setDocuments(payload.documents);
    const targetId = preferredId || payload.documents[0]?.id;
    if (targetId) {
      setActiveDocument(await fetchDocument(targetId));
      setShowCreate(false);
    } else {
      setActiveDocument(null);
      setShowCreate(true);
    }
  }, []);

  useEffect(() => {
    if (!sessionToken()) return;
    setAuthenticated(true);
    refreshList().catch(() => {
      clearSession();
      setAuthenticated(false);
    });
  }, [refreshList]);

  async function login(email: string, password: string, totpCode: string) {
    setBusy(true);
    setError("");
    try {
      const result = await api<{ session_token: string }>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password, totp_code: totpCode }),
      });
      storeSession(result.session_token);
      setAuthenticated(true);
      await refreshList();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to sign in");
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    try {
      await api<void>("/api/v1/auth/logout", { method: "POST" });
    } finally {
      clearSession();
      setAuthenticated(false);
      setDocuments([]);
      setActiveDocument(null);
    }
  }

  async function createDocument(form: FormData) {
    setBusy(true);
    setError("");
    try {
      const result = await api<{ document: PaperDocument }>("/api/v1/documents", { method: "POST", body: form });
      setActiveDocument(result.document);
      await refreshList(result.document.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to create document");
    } finally {
      setBusy(false);
    }
  }

  if (!authenticated) return <LoginScreen busy={busy} error={error} onLogin={login} />;
  if (showCreate || !activeDocument) {
    return <CreateDocument busy={busy} error={error} documents={documents} onCreate={createDocument} onOpen={(id) => refreshList(id)} onLogout={logout} />;
  }
  return (
    <Workspace
      document={activeDocument}
      documents={documents}
      onDocumentChange={setActiveDocument}
      onRefresh={() => refreshList(activeDocument.id)}
      onOpen={(id) => refreshList(id)}
      onNew={() => setShowCreate(true)}
      onDeleted={() => refreshList()}
      onLogout={logout}
    />
  );
}
