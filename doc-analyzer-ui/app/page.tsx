"use client";
import { useState, useRef } from "react";

interface Source {
  page: number;
  similarity: number;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
}

interface UploadedDoc {
  document_id: string;
  filename: string;
  pages: number;
  chunks: number;
}

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Home() {
  const [doc, setDoc] = useState<UploadedDoc | null>(null);
  const [uploading, setUploading] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const uploadFile = async (file: File) => {
    setUploading(true);
    setUploadError("");
    setDoc(null);
    setMessages([]);

    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${API}/upload`, { method: "POST", body: form });
      if (!res.ok) throw new Error("Upload failed");
      const data = await res.json();
      setDoc(data);
    } catch {
      setUploadError("Upload failed. Is the backend running?");
    } finally {
      setUploading(false);
    }
  };

  const askQuestion = async () => {
    if (!question.trim() || asking) return;
    const q = question.trim();
    setQuestion("");
    setMessages((prev) => [...prev, { role: "user", content: q }]);
    setAsking(true);

    try {
      const res = await fetch(`${API}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, document_id: doc?.document_id }),
      });
      if (!res.ok) throw new Error("Ask failed");
      const data = await res.json();
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.answer,
          sources: data.sources,
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

  return (
    <main className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-2xl font-semibold text-gray-900">
            Smart Document Analyzer
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Upload a PDF and ask questions — powered by Claude + pgvector
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left — Upload panel */}
          <div className="lg:col-span-1 flex flex-col gap-4">
            {/* Drop zone */}
            <div
              onClick={() => fileRef.current?.click()}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                const file = e.dataTransfer.files[0];
                if (file?.name.endsWith(".pdf")) uploadFile(file);
              }}
              className="border-2 border-dashed border-gray-200 rounded-xl p-8 text-center cursor-pointer hover:border-blue-300 hover:bg-blue-50 transition-colors"
            >
              <div className="text-3xl mb-3">📄</div>
              <p className="text-sm font-medium text-gray-700">
                {uploading ? "Uploading..." : "Click or drag a PDF here"}
              </p>
              <p className="text-xs text-gray-400 mt-1">PDF files only</p>
              <input
                ref={fileRef}
                type="file"
                accept=".pdf"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) uploadFile(file);
                }}
              />
            </div>

            {uploadError && (
              <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
                {uploadError}
              </p>
            )}

            {/* Document info */}
            {doc && (
              <div className="bg-white border border-gray-200 rounded-xl p-4">
                <div className="flex items-center gap-2 mb-3">
                  <div className="w-2 h-2 rounded-full bg-green-500"></div>
                  <span className="text-sm font-medium text-gray-700">
                    Document ready
                  </span>
                </div>
                <p className="text-sm text-gray-900 font-medium truncate">
                  {doc.filename}
                </p>
                <div className="flex gap-4 mt-2">
                  <div>
                    <div className="text-xs text-gray-400">Pages</div>
                    <div className="text-sm font-medium text-gray-700">
                      {doc.pages}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-400">Chunks</div>
                    <div className="text-sm font-medium text-gray-700">
                      {doc.chunks}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Tips */}
            {!doc && !uploading && (
              <div className="bg-white border border-gray-200 rounded-xl p-4">
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
                  How it works
                </p>
                <div className="flex flex-col gap-2">
                  {[
                    "Upload any PDF document",
                    "Ask questions in plain English",
                    "AI answers from your document only",
                    "Sources cited with page numbers",
                  ].map((tip, i) => (
                    <div key={i} className="flex items-start gap-2">
                      <span className="text-blue-400 text-xs mt-0.5">→</span>
                      <span className="text-xs text-gray-500">{tip}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Right — Chat panel */}
          <div
            className="lg:col-span-2 flex flex-col bg-white border border-gray-200 rounded-xl overflow-hidden"
            style={{ minHeight: "520px" }}
          >
            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-4">
              {messages.length === 0 && (
                <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">
                  {doc
                    ? "Ask a question about your document"
                    : "Upload a document to get started"}
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
                      <div className="flex gap-2 mt-2 flex-wrap">
                        {msg.sources.map((s, j) => (
                          <span
                            key={j}
                            className="text-xs bg-white border border-gray-200 text-gray-500 px-2 py-0.5 rounded-full"
                          >
                            Page {s.page} · {Math.round(s.similarity * 100)}%
                          </span>
                        ))}
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
                  doc
                    ? "Ask a question about your document..."
                    : "Upload a document first"
                }
                disabled={!doc || asking}
                className="flex-1 text-sm border border-gray-200 rounded-lg px-4 py-2.5 bg-gray-50 text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
              />
              <button
                onClick={askQuestion}
                disabled={!doc || asking || !question.trim()}
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
