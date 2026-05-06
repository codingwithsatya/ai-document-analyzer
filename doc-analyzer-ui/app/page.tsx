"use client";
import { useState, useRef, useEffect } from "react";

interface Source {
  page: number;
  similarity?: number;
  rerank_score?: number;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  confidence?: number;
}

interface Document {
  id: string;
  name: string;
  size_bytes: number;
  created_at: string;
}

interface UploadedDoc {
  document_id: string;
  filename: string;
  pages: number;
  chunks: number;
}

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  return `${(bytes / 1024).toFixed(1)} KB`;
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

export default function Home() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [activeDocId, setActiveDocId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [deleting, setDeleting] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchDocuments();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const fetchDocuments = async () => {
    try {
      const res = await fetch(`${API}/documents`);
      const data = await res.json();
      setDocuments(data.documents || []);
      if (data.documents?.length > 0 && !activeDocId) {
        setActiveDocId(data.documents[0].id);
      }
    } catch {
      console.error("Failed to fetch documents");
    }
  };

  const uploadFile = async (file: File) => {
    setUploading(true);
    setUploadError("");

    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${API}/upload`, { method: "POST", body: form });
      if (!res.ok) throw new Error("Upload failed");
      const data: UploadedDoc = await res.json();
      setActiveDocId(data.document_id);
      setMessages([]);
      await fetchDocuments();
    } catch {
      setUploadError("Upload failed. Is the backend running?");
    } finally {
      setUploading(false);
    }
  };

  const deleteDocument = async (docId: string) => {
    setDeleting(docId);
    try {
      await fetch(`${API}/documents/${docId}`, { method: "DELETE" });
      if (activeDocId === docId) {
        setActiveDocId(null);
        setMessages([]);
      }
      await fetchDocuments();
    } catch {
      console.error("Delete failed");
    } finally {
      setDeleting(null);
    }
  };

  const askQuestion = async () => {
    if (!question.trim() || asking || !activeDocId) return;
    const q = question.trim();
    setQuestion("");
    setMessages((prev) => [...prev, { role: "user", content: q }]);
    setAsking(true);

    try {
      const res = await fetch(`${API}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, document_id: activeDocId }),
      });
      if (!res.ok) throw new Error("Ask failed");
      const data = await res.json();
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.answer,
          sources: data.sources,
          confidence: data.confidence,
        },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Something went wrong. Please try again.",
        },
      ]);
    } finally {
      setAsking(false);
    }
  };

  const activeDoc = documents.find((d) => d.id === activeDocId);

  return (
    <main className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-gray-900">
              Smart Document Analyzer
            </h1>
            <p className="text-sm text-gray-500 mt-1">
              Upload PDFs and ask questions — hybrid search + Cohere reranking
            </p>
          </div>
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-40 transition-colors"
          >
            {uploading ? "Uploading..." : "+ Upload PDF"}
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) uploadFile(f);
            }}
          />
        </div>

        {uploadError && (
          <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-3 mb-4">
            {uploadError}
          </p>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Left — Document list */}
          <div className="lg:col-span-1 flex flex-col gap-3">
            <div className="text-xs font-medium text-gray-400 uppercase tracking-wide">
              Documents ({documents.length})
            </div>

            {documents.length === 0 && (
              <div
                onClick={() => fileRef.current?.click()}
                className="border-2 border-dashed border-gray-200 rounded-xl p-6 text-center cursor-pointer hover:border-blue-300 hover:bg-blue-50 transition-colors"
              >
                <div className="text-2xl mb-2">📄</div>
                <p className="text-xs text-gray-500">
                  Click to upload your first PDF
                </p>
              </div>
            )}

            {documents.map((doc) => (
              <div
                key={doc.id}
                onClick={() => {
                  setActiveDocId(doc.id);
                  setMessages([]);
                }}
                className={`bg-white border rounded-xl p-3 cursor-pointer transition-all group ${
                  activeDocId === doc.id
                    ? "border-blue-400 ring-1 ring-blue-400"
                    : "border-gray-200 hover:border-gray-300"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-800 truncate">
                      {doc.name}
                    </p>
                    <p className="text-xs text-gray-400 mt-0.5">
                      {formatBytes(doc.size_bytes)} ·{" "}
                      {formatDate(doc.created_at)}
                    </p>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteDocument(doc.id);
                    }}
                    disabled={deleting === doc.id}
                    className="text-gray-300 hover:text-red-400 transition-colors text-xs opacity-0 group-hover:opacity-100 flex-shrink-0"
                  >
                    {deleting === doc.id ? "..." : "✕"}
                  </button>
                </div>
                {activeDocId === doc.id && (
                  <div className="mt-2 flex items-center gap-1.5">
                    <div className="w-1.5 h-1.5 rounded-full bg-blue-500"></div>
                    <span className="text-xs text-blue-600 font-medium">
                      Active
                    </span>
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Right — Chat panel */}
          <div
            className="lg:col-span-3 flex flex-col bg-white border border-gray-200 rounded-xl overflow-hidden"
            style={{ minHeight: "560px" }}
          >
            {/* Chat header */}
            {activeDoc && (
              <div className="border-b border-gray-100 px-5 py-3 flex items-center gap-2">
                <span className="text-xs text-gray-400">Querying:</span>
                <span className="text-xs font-medium text-gray-700">
                  {activeDoc.name}
                </span>
                <span className="text-xs text-gray-300">·</span>
                <span className="text-xs text-gray-400">
                  hybrid search + reranking
                </span>
              </div>
            )}

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-4">
              {messages.length === 0 && (
                <div className="flex-1 flex flex-col items-center justify-center text-center gap-3">
                  <div className="text-3xl">💬</div>
                  <p className="text-sm text-gray-400">
                    {activeDocId
                      ? "Ask anything about this document"
                      : "Select or upload a document to get started"}
                  </p>
                </div>
              )}

              {messages.map((msg, i) => (
                <div
                  key={i}
                  className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[85%] rounded-xl px-4 py-3 text-sm leading-relaxed ${
                      msg.role === "user"
                        ? "bg-blue-600 text-white"
                        : "bg-gray-50 border border-gray-200 text-gray-800"
                    }`}
                  >
                    <p style={{ whiteSpace: "pre-wrap" }}>{msg.content}</p>

                    {msg.sources && msg.sources.length > 0 && (
                      <div className="mt-2 flex flex-col gap-1.5">
                        <div className="flex gap-2 flex-wrap">
                          {msg.sources.map((s, j) => (
                            <span
                              key={j}
                              className="text-xs bg-white border border-gray-200 text-gray-500 px-2 py-0.5 rounded-full"
                            >
                              Page {s.page} ·{" "}
                              {Math.round(
                                (s.rerank_score ?? s.similarity ?? 0) * 100,
                              )}
                              % relevance
                            </span>
                          ))}
                        </div>
                        {msg.confidence !== undefined && (
                          <span className="text-xs text-gray-400">
                            Confidence: {Math.round(msg.confidence * 100)}%
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {asking && (
                <div className="flex justify-start">
                  <div className="bg-gray-50 border border-gray-200 rounded-xl px-4 py-3 text-sm text-gray-400">
                    Searching document...
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div className="border-t border-gray-200 p-4 flex gap-3">
              <input
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) =>
                  e.key === "Enter" && !e.shiftKey && askQuestion()
                }
                placeholder={
                  activeDocId
                    ? "Ask a question about this document..."
                    : "Select a document first"
                }
                disabled={!activeDocId || asking}
                className="flex-1 text-sm border border-gray-200 rounded-lg px-4 py-2.5 bg-gray-50 text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
              />
              <button
                onClick={askQuestion}
                disabled={!activeDocId || asking || !question.trim()}
                className="px-5 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Ask
              </button>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
