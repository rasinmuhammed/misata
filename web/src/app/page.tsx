"use client";

import { useState } from "react";
import {
  Sparkles,
  Database,
  BarChart3,
  Settings2,
  Download,
  Play,
  Zap,
  ChevronRight,
  Loader2,
  CheckCircle,
  Table,
  GitBranch,
  TrendingUp,
} from "lucide-react";

// API URL (change for production)
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type TabType = "story" | "graph" | "visual";

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
    <div className="min-h-screen">
      {/* Header */}
      <header className="border-b border-white/10 backdrop-blur-lg bg-gray-950/50 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500 to-cyan-500 flex items-center justify-center">
              <Sparkles className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold gradient-text">Misata</h1>
              <p className="text-xs text-gray-500">AI-Powered Synthetic Data</p>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <a
              href="/docs"
              className="text-sm text-gray-400 hover:text-white transition"
            >
              Docs
            </a>
            <a
              href="https://github.com"
              className="text-sm text-gray-400 hover:text-white transition"
            >
              GitHub
            </a>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-6 py-12">
        {/* Hero Section */}
        <div className="text-center mb-12">
          <h2 className="text-4xl md:text-5xl font-bold mb-4">
            <span className="gradient-text">Generate Realistic Data</span>
            <br />
            <span className="text-white">From Natural Language</span>
          </h2>
          <p className="text-gray-400 text-lg max-w-2xl mx-auto">
            Describe your data needs in plain English. Misata uses AI to create
            industry-realistic synthetic data indistinguishable from the real thing.
          </p>
        </div>

        {/* Mode Tabs */}
        <div className="flex justify-center gap-2 mb-8">
          <button
            onClick={() => setActiveTab("story")}
            className={`tab-item flex items-center gap-2 ${activeTab === "story" ? "active" : ""}`}
          >
            <Sparkles className="w-4 h-4" />
            Story Mode
          </button>
          <button
            onClick={() => setActiveTab("graph")}
            className={`tab-item flex items-center gap-2 ${activeTab === "graph" ? "active" : ""}`}
          >
            <BarChart3 className="w-4 h-4" />
            Graph Mode
          </button>
          <button
            onClick={() => setActiveTab("visual")}
            className={`tab-item flex items-center gap-2 ${activeTab === "visual" ? "active" : ""}`}
          >
            <Database className="w-4 h-4" />
            Visual Builder
          </button>
        </div>

        {/* Error Display */}
        {error && (
          <div className="mb-8 p-4 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400">
            {error === "Groq API key required. Set GROQ_API_KEY environment variable or pass api_key parameter. Get your key at: https://console.groq.com" ? (
              <div>
                <p className="font-medium">API Key Required</p>
                <p className="text-sm mt-1">
                  Please set your GROQ_API_KEY environment variable.
                  <a href="https://console.groq.com" className="underline ml-1" target="_blank" rel="noopener noreferrer">
                    Get your free key here
                  </a>
                </p>
              </div>
            ) : (
              error
            )}
          </div>
        )}

        <div className="grid lg:grid-cols-2 gap-8">
          {/* Input Panel */}
          <div className="glass-card p-6">
            <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
              {activeTab === "story" && <><Sparkles className="w-5 h-5 text-purple-400" /> Describe Your Data</>}
              {activeTab === "graph" && <><BarChart3 className="w-5 h-5 text-cyan-400" /> Describe Your Chart</>}
              {activeTab === "visual" && <><Database className="w-5 h-5 text-green-400" /> Visual Schema Builder</>}
            </h3>

            {activeTab === "story" && (
              <>
                <textarea
                  className="textarea-modern mb-4"
                  placeholder="Example: A mobile fitness app with 50K users tracking workouts (running, cycling, yoga). Heavy signups in January due to New Year's resolutions, dropping 60% by March. 15% premium conversion at $9.99/month."
                  value={story}
                  onChange={(e) => setStory(e.target.value)}
                  rows={6}
                />
                <div className="space-y-2 mb-4 text-sm text-gray-400">
                  <p className="font-medium text-gray-300">Pro Tips:</p>
                  <ul className="space-y-1 ml-4 list-disc">
                    <li>Mention specific numbers: &ldquo;50K users&rdquo;, &ldquo;$1M revenue&rdquo;</li>
                    <li>Describe temporal patterns: &ldquo;20% churn in Q3&rdquo;</li>
                    <li>Specify relationships: &ldquo;users have multiple orders&rdquo;</li>
                    <li>Include industry context: &ldquo;SaaS&rdquo;, &ldquo;e-commerce&rdquo;, &ldquo;healthcare&rdquo;</li>
                  </ul>
                </div>
              </>
            )}

            {activeTab === "graph" && (
              <>
                <textarea
                  className="textarea-modern mb-4"
                  placeholder="Example: Monthly revenue line chart showing:
- Start: $100K in Jan 2023
- End: $1M by Dec 2024
- Exponential growth curve
- 20% seasonal dip every Q2 (summer slowdown)
- One-time 50% crash in Oct 2023 with 3-month recovery"
                  value={graphDescription}
                  onChange={(e) => setGraphDescription(e.target.value)}
                  rows={8}
                />
                <div className="p-4 rounded-xl bg-cyan-500/10 border border-cyan-500/30">
                  <p className="text-cyan-400 font-medium flex items-center gap-2">
                    <TrendingUp className="w-4 h-4" />
                    Reverse Engineering Mode
                  </p>
                  <p className="text-sm text-gray-400 mt-1">
                    Describe the chart you want. We&apos;ll generate data that produces exactly that pattern when plotted.
                  </p>
                </div>
              </>
            )}

            {activeTab === "visual" && (
              <div className="p-8 text-center text-gray-500">
                <Database className="w-12 h-12 mx-auto mb-4 opacity-50" />
                <p>Visual schema builder coming soon!</p>
                <p className="text-sm mt-2">Use Story Mode or Graph Mode for now.</p>
              </div>
            )}

            {activeTab !== "visual" && (
              <button
                onClick={generateSchema}
                disabled={isGeneratingSchema || (activeTab === "story" ? !story : !graphDescription)}
                className="btn-primary w-full flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isGeneratingSchema ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    Generating with AI...
                  </>
                ) : (
                  <>
                    <Zap className="w-5 h-5" />
                    Generate Schema
                  </>
                )}
              </button>
            )}
          </div>

          {/* Schema Preview Panel */}
          <div className="glass-card p-6">
            <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
              <GitBranch className="w-5 h-5 text-purple-400" />
              Generated Schema
            </h3>

            {!schema ? (
              <div className="p-12 text-center text-gray-500">
                <Database className="w-12 h-12 mx-auto mb-4 opacity-30" />
                <p>Your schema will appear here</p>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="p-4 rounded-xl bg-purple-500/10 border border-purple-500/30">
                  <h4 className="font-semibold text-purple-400">{schema.name}</h4>
                  {schema.description && (
                    <p className="text-sm text-gray-400 mt-1">{schema.description}</p>
                  )}
                </div>

                {/* Stats */}
                <div className="grid grid-cols-3 gap-3">
                  <div className="stat-card">
                    <div className="value">{schema.tables.length}</div>
                    <div className="label">Tables</div>
                  </div>
                  <div className="stat-card">
                    <div className="value">{schema.relationships.length}</div>
                    <div className="label">Relationships</div>
                  </div>
                  <div className="stat-card">
                    <div className="value">{schema.events.length}</div>
                    <div className="label">Events</div>
                  </div>
                </div>

                {/* Tables */}
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {schema.tables.map((table) => (
                    <div key={table.name} className="schema-node">
                      <div className="schema-node-title flex items-center justify-between">
                        <span className="flex items-center gap-2">
                          <Table className="w-4 h-4" />
                          {table.name}
                        </span>
                        <span className="text-xs text-gray-400">
                          {table.row_count.toLocaleString()} rows
                        </span>
                      </div>
                      <div className="mt-2 space-y-1">
                        {schema.columns[table.name]?.slice(0, 4).map((col) => (
                          <div key={col.name} className="schema-node-column flex items-center gap-2">
                            <span className="w-2 h-2 rounded-full bg-purple-500/50" />
                            <span>{col.name}</span>
                            <span className="text-xs text-gray-500">({col.type})</span>
                          </div>
                        ))}
                        {schema.columns[table.name]?.length > 4 && (
                          <div className="text-xs text-gray-500 ml-4">
                            +{schema.columns[table.name].length - 4} more columns
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
                  className="btn-primary w-full flex items-center justify-center gap-2 disabled:opacity-50"
                >
                  {isGeneratingData ? (
                    <>
                      <Loader2 className="w-5 h-5 animate-spin" />
                      Generating Data...
                    </>
                  ) : (
                    <>
                      <Play className="w-5 h-5" />
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
          <div className="mt-8 glass-card p-6">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-lg font-semibold flex items-center gap-2">
                <CheckCircle className="w-5 h-5 text-green-400" />
                Data Generated Successfully!
              </h3>
              <button onClick={downloadData} className="btn-primary flex items-center gap-2">
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
                  className={`px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition ${activePreviewTable === tableName
                      ? "bg-purple-500 text-white"
                      : "bg-white/5 text-gray-400 hover:bg-white/10"
                    }`}
                >
                  {tableName}
                  <span className="ml-2 text-xs opacity-70">
                    ({dataPreview.stats[tableName].row_count.toLocaleString()} rows)
                  </span>
                </button>
              ))}
            </div>

            {/* Stats for Active Table */}
            {activePreviewTable && dataPreview.stats[activePreviewTable] && (
              <div className="grid grid-cols-4 gap-4 mb-4">
                <div className="p-3 rounded-lg bg-white/5">
                  <div className="text-2xl font-bold text-purple-400">
                    {dataPreview.stats[activePreviewTable].row_count.toLocaleString()}
                  </div>
                  <div className="text-xs text-gray-500">Total Rows</div>
                </div>
                <div className="p-3 rounded-lg bg-white/5">
                  <div className="text-2xl font-bold text-cyan-400">
                    {dataPreview.stats[activePreviewTable].columns.length}
                  </div>
                  <div className="text-xs text-gray-500">Columns</div>
                </div>
                <div className="p-3 rounded-lg bg-white/5">
                  <div className="text-2xl font-bold text-green-400">
                    {dataPreview.stats[activePreviewTable].memory_mb.toFixed(2)}
                  </div>
                  <div className="text-xs text-gray-500">Memory (MB)</div>
                </div>
                <div className="p-3 rounded-lg bg-white/5">
                  <div className="text-2xl font-bold text-orange-400">
                    {Object.keys(dataPreview.stats[activePreviewTable].numeric_stats).length}
                  </div>
                  <div className="text-xs text-gray-500">Numeric Cols</div>
                </div>
              </div>
            )}

            {/* Data Table */}
            {activePreviewTable && (
              <div className="table-preview">
                <table>
                  <thead>
                    <tr>
                      {dataPreview.stats[activePreviewTable]?.columns.map((col) => (
                        <th key={col}>{col}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {dataPreview.tables[activePreviewTable]?.slice(0, 10).map((row, idx) => (
                      <tr key={idx}>
                        {dataPreview.stats[activePreviewTable]?.columns.map((col) => (
                          <td key={col}>{String(row[col] ?? "")}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {dataPreview.tables[activePreviewTable]?.length > 10 && (
                  <div className="text-center py-3 text-sm text-gray-500">
                    Showing 10 of {dataPreview.tables[activePreviewTable].length} preview rows
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Feature Cards */}
        <div className="mt-16 grid md:grid-cols-3 gap-6">
          <div className="glass-card p-6 text-center">
            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-purple-500/20 to-purple-500/10 flex items-center justify-center mx-auto mb-4">
              <Sparkles className="w-6 h-6 text-purple-400" />
            </div>
            <h3 className="font-semibold mb-2">AI-Powered</h3>
            <p className="text-sm text-gray-400">
              Llama 3.3 understands your industry context and generates realistic schemas
            </p>
          </div>
          <div className="glass-card p-6 text-center">
            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-cyan-500/20 to-cyan-500/10 flex items-center justify-center mx-auto mb-4">
              <BarChart3 className="w-6 h-6 text-cyan-400" />
            </div>
            <h3 className="font-semibold mb-2">Graph Reverse Engineering</h3>
            <p className="text-sm text-gray-400">
              Describe your desired chart pattern and get matching data
            </p>
          </div>
          <div className="glass-card p-6 text-center">
            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-green-500/20 to-green-500/10 flex items-center justify-center mx-auto mb-4">
              <Zap className="w-6 h-6 text-green-400" />
            </div>
            <h3 className="font-semibold mb-2">Blazing Fast</h3>
            <p className="text-sm text-gray-400">
              Generate millions of rows in seconds with vectorized operations
            </p>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-white/10 mt-20 py-8">
        <div className="max-w-7xl mx-auto px-6 text-center text-gray-500 text-sm">
          <p>Built with ❤️ by Muhammed Rasin</p>
          <p className="mt-1">Powered by Groq Llama 3.3 • NumPy • Pandas • Mimesis</p>
        </div>
      </footer>
    </div>
  );
}
