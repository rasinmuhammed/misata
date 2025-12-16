"use client";

import { useState } from "react";
import {
  Database,
  BarChart3,
  Download,
  Play,
  ChevronRight,
  Check,
  Table,
  ArrowRight,
} from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type TabType = "story" | "graph";

interface SchemaConfig {
  name: string;
  description?: string;
  tables: Array<{
    name: string;
    row_count: number;
    description?: string;
  }>;
  columns: Record<string, Array<{
    name: string;
    type: string;
    distribution_params: Record<string, unknown>;
  }>>;
  relationships: Array<{
    parent_table: string;
    child_table: string;
  }>;
  events: Array<{
    name: string;
    description?: string;
  }>;
}

interface DataPreview {
  tables: Record<string, Array<Record<string, unknown>>>;
  stats: Record<string, {
    row_count: number;
    columns: string[];
    memory_mb: number;
    numeric_stats: Record<string, { mean: number; std: number; min: number; max: number }>;
  }>;
  download_id: string;
}

export default function Home() {
  const [activeTab, setActiveTab] = useState<TabType>("story");
  const [story, setStory] = useState("");
  const [graphDescription, setGraphDescription] = useState("");
  const [schema, setSchema] = useState<SchemaConfig | null>(null);
  const [dataPreview, setDataPreview] = useState<DataPreview | null>(null);
  const [isGeneratingSchema, setIsGeneratingSchema] = useState(false);
  const [isGeneratingData, setIsGeneratingData] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activePreviewTable, setActivePreviewTable] = useState<string | null>(null);

  const generateSchema = async () => {
    setIsGeneratingSchema(true);
    setError(null);

    try {
      const endpoint = activeTab === "story"
        ? "/api/generate-schema"
        : "/api/generate-from-graph";

      const body = activeTab === "story"
        ? { story, default_rows: 10000 }
        : { description: graphDescription };

      const response = await fetch(`${API_URL}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to generate schema");
      }

      const data = await response.json();
      setSchema(data.schema_config);
      if (data.schema_config.tables.length > 0) {
        setActivePreviewTable(data.schema_config.tables[0].name);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "An error occurred");
    } finally {
      setIsGeneratingSchema(false);
    }
  };

  const generateData = async () => {
    if (!schema) return;

    setIsGeneratingData(true);
    setError(null);

    try {
      const response = await fetch(`${API_URL}/api/generate-data`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ schema_config: schema }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to generate data");
      }

      const data = await response.json();
      setDataPreview(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "An error occurred");
    } finally {
      setIsGeneratingData(false);
    }
  };

  const downloadData = () => {
    if (!dataPreview) return;
    window.open(`${API_URL}/api/download/${dataPreview.download_id}?format=csv`, "_blank");
  };

  return (
    <div className="min-h-screen bg-[var(--background)]">
      {/* Header */}
      <header className="border-b border-[var(--border-subtle)] sticky top-0 z-50 bg-[var(--background)]">
        <div className="container py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-[var(--foreground)] flex items-center justify-center">
              <Database className="w-4 h-4 text-[var(--background)]" />
            </div>
            <span className="text-lg font-semibold tracking-tight">Misata</span>
          </div>

          <nav className="flex items-center gap-6">
            <a href="/docs" className="text-sm text-[var(--muted)] hover:text-[var(--foreground)] transition-colors">
              Documentation
            </a>
            <a href="https://github.com" className="text-sm text-[var(--muted)] hover:text-[var(--foreground)] transition-colors">
              GitHub
            </a>
          </nav>
        </div>
      </header>

      {/* Main Content */}
      <main className="container py-16">
        {/* Hero */}
        <div className="max-w-2xl mx-auto text-center mb-16">
          <h1 className="text-4xl font-semibold tracking-tight mb-4">
            Synthetic data from natural language
          </h1>
          <p className="text-[var(--muted)] text-lg">
            Describe your data needs in plain English. Generate realistic,
            statistically valid datasets in seconds.
          </p>
        </div>

        {/* Mode Tabs */}
        <div className="flex justify-center mb-10">
          <div className="tabs">
            <button
              onClick={() => setActiveTab("story")}
              className={`tab ${activeTab === "story" ? "active" : ""}`}
            >
              Story Mode
            </button>
            <button
              onClick={() => setActiveTab("graph")}
              className={`tab ${activeTab === "graph" ? "active" : ""}`}
            >
              Graph Mode
            </button>
          </div>
        </div>

        {/* Error Display */}
        {error && (
          <div className="max-w-3xl mx-auto mb-8">
            <div className="alert alert-error">
              {error.includes("GROQ_API_KEY") ? (
                <>
                  <strong>API Key Required:</strong> Set your GROQ_API_KEY environment variable.{" "}
                  <a href="https://console.groq.com" className="underline" target="_blank" rel="noopener noreferrer">
                    Get a free key
                  </a>
                </>
              ) : (
                error
              )}
            </div>
          </div>
        )}

        <div className="grid lg:grid-cols-2 gap-8 max-w-5xl mx-auto">
          {/* Input Panel */}
          <div className="card">
            <h3 className="font-semibold mb-4">
              {activeTab === "story" ? "Describe your data" : "Describe your chart"}
            </h3>

            {activeTab === "story" ? (
              <textarea
                className="textarea mb-4"
                placeholder="A fitness app with 50K users tracking workouts. 15% premium conversion at $9.99/month. Heavy signups in January, 60% drop by March."
                value={story}
                onChange={(e) => setStory(e.target.value)}
                rows={6}
              />
            ) : (
              <textarea
                className="textarea mb-4"
                placeholder="Monthly revenue chart: Start at $100K in Jan 2023, grow exponentially to $1M by Dec 2024. Include 20% seasonal dips in Q2."
                value={graphDescription}
                onChange={(e) => setGraphDescription(e.target.value)}
                rows={6}
              />
            )}

            <button
              onClick={generateSchema}
              disabled={isGeneratingSchema || (activeTab === "story" ? !story : !graphDescription)}
              className="btn btn-primary w-full"
            >
              {isGeneratingSchema ? (
                <>
                  <span className="spinner" />
                  Generating...
                </>
              ) : (
                <>
                  Generate Schema
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </div>

          {/* Schema Preview Panel */}
          <div className="card">
            <h3 className="font-semibold mb-4">Generated Schema</h3>

            {!schema ? (
              <div className="empty-state">
                <Database className="w-10 h-10 mx-auto" />
                <p>Your schema will appear here</p>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h4 className="font-medium">{schema.name}</h4>
                    {schema.description && (
                      <p className="text-sm text-[var(--muted)]">{schema.description}</p>
                    )}
                  </div>
                </div>

                {/* Stats */}
                <div className="stat-grid">
                  <div className="stat">
                    <div className="stat-value">{schema.tables.length}</div>
                    <div className="stat-label">Tables</div>
                  </div>
                  <div className="stat">
                    <div className="stat-value">{schema.relationships.length}</div>
                    <div className="stat-label">Relationships</div>
                  </div>
                  <div className="stat">
                    <div className="stat-value">{schema.events.length}</div>
                    <div className="stat-label">Events</div>
                  </div>
                </div>

                {/* Tables */}
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {schema.tables.map((table) => (
                    <div key={table.name} className="schema-node">
                      <div className="schema-node-title">
                        <span className="flex items-center gap-2">
                          <Table className="w-4 h-4 text-[var(--muted)]" />
                          {table.name}
                        </span>
                        <span className="text-xs text-[var(--muted)] font-normal">
                          {table.row_count.toLocaleString()} rows
                        </span>
                      </div>
                      <div className="mt-2 space-y-1.5">
                        {schema.columns[table.name]?.slice(0, 5).map((col) => {
                          // Format distribution rules for display
                          const rules: string[] = [];
                          const params = col.distribution_params || {};

                          if (params.min !== undefined && params.max !== undefined) {
                            rules.push(`${params.min}-${params.max}`);
                          }
                          if (params.choices && Array.isArray(params.choices)) {
                            const choices = params.choices as string[];
                            rules.push(`[${choices.slice(0, 3).join(", ")}${choices.length > 3 ? "..." : ""}]`);
                          }
                          if (params.text_type && typeof params.text_type === "string") {
                            rules.push(params.text_type);
                          }
                          if (params.start && params.end && typeof params.start === "string" && typeof params.end === "string") {
                            rules.push(`${params.start.slice(0, 10)} → ${params.end.slice(0, 10)}`);
                          }
                          if (params.distribution && params.distribution !== "normal") {
                            rules.push(String(params.distribution));
                          }

                          return (
                            <div key={col.name} className="schema-node-column">
                              <span className="dot" />
                              <span className="font-medium">{col.name}</span>
                              <span className="text-[var(--muted)]">({col.type})</span>
                              {rules.length > 0 && (
                                <span className="ml-auto text-xs text-[var(--accent)]">
                                  {rules.join(" • ")}
                                </span>
                              )}
                            </div>
                          );
                        })}
                        {schema.columns[table.name]?.length > 5 && (
                          <div className="text-xs text-[var(--muted)] pl-3">
                            +{schema.columns[table.name].length - 5} more columns
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>

                {/* Generate Button */}
                <button
                  onClick={generateData}
                  disabled={isGeneratingData}
                  className="btn btn-primary w-full"
                >
                  {isGeneratingData ? (
                    <>
                      <span className="spinner" />
                      Generating...
                    </>
                  ) : (
                    <>
                      <Play className="w-4 h-4" />
                      Generate Data
                    </>
                  )}
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Data Preview Section */}
        {dataPreview && (
          <div className="max-w-5xl mx-auto mt-10">
            <div className="card">
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-[rgba(34,197,94,0.1)] flex items-center justify-center">
                    <Check className="w-4 h-4 text-[var(--success)]" />
                  </div>
                  <span className="font-semibold">Data Generated</span>
                </div>
                <button onClick={downloadData} className="btn btn-secondary">
                  <Download className="w-4 h-4" />
                  Download CSV
                </button>
              </div>

              {/* Table Selector */}
              <div className="flex gap-2 mb-4 overflow-x-auto pb-2">
                {Object.keys(dataPreview.tables).map((tableName) => (
                  <button
                    key={tableName}
                    onClick={() => setActivePreviewTable(tableName)}
                    className={`px-3 py-1.5 rounded-md text-sm font-medium whitespace-nowrap transition-colors ${activePreviewTable === tableName
                      ? "bg-[var(--foreground)] text-[var(--background)]"
                      : "bg-[var(--card)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                      }`}
                  >
                    {tableName}
                  </button>
                ))}
              </div>

              {/* Data Table */}
              {activePreviewTable && (
                <div className="table-container">
                  <table>
                    <thead>
                      <tr>
                        {dataPreview.stats[activePreviewTable]?.columns.map((col) => (
                          <th key={col}>{col}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {dataPreview.tables[activePreviewTable]?.slice(0, 8).map((row, idx) => (
                        <tr key={idx}>
                          {dataPreview.stats[activePreviewTable]?.columns.map((col) => (
                            <td key={col}>{String(row[col] ?? "")}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {dataPreview.tables[activePreviewTable]?.length > 8 && (
                    <div className="text-center py-3 text-sm text-[var(--muted)]">
                      Showing 8 of {dataPreview.stats[activePreviewTable].row_count.toLocaleString()} rows
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Features */}
        <div className="max-w-4xl mx-auto mt-24 grid md:grid-cols-3 gap-6">
          <div className="text-center">
            <div className="w-10 h-10 rounded-lg bg-[var(--card)] border border-[var(--border-subtle)] flex items-center justify-center mx-auto mb-4">
              <Database className="w-5 h-5 text-[var(--muted-foreground)]" />
            </div>
            <h3 className="font-medium mb-2">Schema Generation</h3>
            <p className="text-sm text-[var(--muted)]">
              AI understands your domain and creates realistic table structures
            </p>
          </div>
          <div className="text-center">
            <div className="w-10 h-10 rounded-lg bg-[var(--card)] border border-[var(--border-subtle)] flex items-center justify-center mx-auto mb-4">
              <BarChart3 className="w-5 h-5 text-[var(--muted-foreground)]" />
            </div>
            <h3 className="font-medium mb-2">Graph Reverse Engineering</h3>
            <p className="text-sm text-[var(--muted)]">
              Describe your desired chart pattern and get matching data
            </p>
          </div>
          <div className="text-center">
            <div className="w-10 h-10 rounded-lg bg-[var(--card)] border border-[var(--border-subtle)] flex items-center justify-center mx-auto mb-4">
              <Play className="w-5 h-5 text-[var(--muted-foreground)]" />
            </div>
            <h3 className="font-medium mb-2">Streaming Generation</h3>
            <p className="text-sm text-[var(--muted)]">
              Generate billions of rows without memory constraints
            </p>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-[var(--border-subtle)] py-8 mt-20">
        <div className="container text-center text-sm text-[var(--muted)]">
          <p>Built by Muhammed Rasin</p>
        </div>
      </footer>
    </div>
  );
}
