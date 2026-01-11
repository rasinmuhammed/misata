"use client";

import { useState, useEffect, useCallback, useMemo, createContext, useContext } from 'react';
import {
    ReactFlow,
    Background,
    Controls,
    MiniMap,
    useNodesState,
    useEdgesState,
    Connection,
    Edge,
    Node,
    ReactFlowProvider,
    Panel,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import {
    Plus,
    Download,
    Play,
    Trash2,
    ChevronDown,
    Sparkles,
    FileJson,
    FileSpreadsheet,
    Database,
    X,
    Settings2,
    TrendingUp,
    Link2,
    CheckCircle2,
    Undo2,
    Redo2,
    Loader2,
    BarChart3,
    Columns,
    Layers,
    Moon,
    Sun,
    Activity,
    Clock,
    Eye,
    ChevronRight,
} from 'lucide-react';

import TableNode from '@/components/TableNode';
import OutcomeCurveEditor from '@/components/OutcomeCurveEditor';
import DataViewer from '@/components/DataViewer';
import QualityReport from '@/components/QualityReport';
import { useSchemaStore } from '@/store/schemaStore';

const nodeTypes = {
    tableNode: TableNode,
};

// Theme context
const ThemeContext = createContext<{
    isDark: boolean;
    toggle: () => void;
}>({ isDark: false, toggle: () => { } });

function useTheme() {
    return useContext(ThemeContext);
}

// Job type
interface Job {
    id: string;
    status: 'PENDING' | 'PROGRESS' | 'SUCCESS' | 'FAILURE';
    progress: number;
    tables: number;
    rows: number;
    createdAt: string;
}

function WorkspaceContent() {
    // Theme
    const [isDark, setIsDark] = useState(false);
    const toggleTheme = useCallback(() => setIsDark((d) => !d), []);

    // Schema store
    const {
        tables,
        relationships,
        outcomeConstraints,
        addTable,
        updateTable,
        removeTable,
        addRelationship,
        removeRelationship,
        getSchemaConfig,
        undo,
        redo,
        history,
        historyIndex,
        clearSchema,
    } = useSchemaStore();

    // Local state
    const [selectedNode, setSelectedNode] = useState<string | null>(null);
    const [showStoryMode, setShowStoryMode] = useState(false);
    const [showCurveEditor, setShowCurveEditor] = useState(false);
    const [curveEditorContext, setCurveEditorContext] = useState<{
        tableId: string;
        columnId: string;
        tableName: string;
        columnName: string;
    } | null>(null);
    const [showDataViewer, setShowDataViewer] = useState(false);
    const [showQualityReport, setShowQualityReport] = useState(false);
    const [qualityReportData, setQualityReportData] = useState<unknown>(null);
    const [currentJobId, setCurrentJobId] = useState<string | null>(null);
    const [isGenerating, setIsGenerating] = useState(false);
    const [story, setStory] = useState('');
    const [previewData, setPreviewData] = useState<Record<string, Record<string, unknown>[]>>({});
    const [selectedPreviewTable, setSelectedPreviewTable] = useState<string | null>(null);
    const [showJobsPanel, setShowJobsPanel] = useState(false);
    const [jobs, setJobs] = useState<Job[]>([]);

    // Load jobs from localStorage
    useEffect(() => {
        const stored = localStorage.getItem('misata_jobs');
        if (stored) {
            try {
                setJobs(JSON.parse(stored));
            } catch { }
        }
    }, []);

    // Convert tables to React Flow nodes
    const initialNodes: Node[] = useMemo(() => {
        return tables.map((table) => ({
            id: table.id,
            type: 'tableNode',
            position: table.position || { x: Math.random() * 400, y: Math.random() * 300 },
            data: {
                ...table,
                label: table.name,
                tableId: table.id,
                onAddColumn: () => {
                    const newColumn = {
                        id: `col_${Date.now()}`,
                        name: `column_${table.columns.length + 1}`,
                        type: 'text' as const,
                    };
                    updateTable(table.id, {
                        columns: [...table.columns, newColumn],
                    });
                },
            },
        }));
    }, [tables, updateTable]);

    // Convert relationships to edges
    const initialEdges: Edge[] = useMemo(() => {
        return relationships.map((rel) => {
            const sourceTable = tables.find((t) => t.name === rel.parentTable || t.id === rel.parentTable);
            const targetTable = tables.find((t) => t.name === rel.childTable || t.id === rel.childTable);
            return {
                id: rel.id,
                source: sourceTable?.id || rel.parentTable,
                target: targetTable?.id || rel.childTable,
                sourceHandle: `${rel.parentKey}-source`,
                targetHandle: `${rel.childKey}-target`,
                type: 'smoothstep',
                animated: true,
                style: { stroke: isDark ? '#A3B18A' : '#588157', strokeWidth: 2 },
                markerEnd: { type: 'arrowclosed' as const, color: isDark ? '#A3B18A' : '#588157' },
            };
        });
    }, [relationships, tables, isDark]);

    const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

    useEffect(() => {
        setNodes(initialNodes);
    }, [initialNodes, setNodes]);

    useEffect(() => {
        setEdges(initialEdges);
    }, [initialEdges, setEdges]);

    const onNodeDragStop = useCallback(
        (_: unknown, node: Node) => {
            updateTable(node.id, { position: node.position });
        },
        [updateTable]
    );

    const onConnect = useCallback(
        (connection: Connection) => {
            if (connection.source && connection.target) {
                const sourceTable = tables.find((t) => t.id === connection.source);
                const targetTable = tables.find((t) => t.id === connection.target);
                if (sourceTable && targetTable) {
                    addRelationship({
                        id: `rel_${Date.now()}`,
                        parentTable: sourceTable.name,
                        childTable: targetTable.name,
                        parentKey: connection.sourceHandle?.replace('-source', '') || 'id',
                        childKey: connection.targetHandle?.replace('-target', '') || `${sourceTable.name}_id`,
                    });
                }
            }
        },
        [tables, addRelationship]
    );

    const onNodeClick = useCallback((_: unknown, node: Node) => {
        setSelectedNode(node.id);
    }, []);

    const selectedTable = useMemo(() => {
        return tables.find((t) => t.id === selectedNode);
    }, [tables, selectedNode]);

    const handleAddTable = () => {
        const tableNum = tables.length + 1;
        addTable({
            id: `table_${Date.now()}`,
            name: `table_${tableNum}`,
            columns: [{ id: `col_${Date.now()}`, name: 'id', type: 'int' as const }],
            position: { x: 100 + (tables.length % 3) * 300, y: 100 + Math.floor(tables.length / 3) * 250 },
            rowCount: 100,
        });
    };

    const handleGenerate = async () => {
        if (tables.length === 0) return;
        setIsGenerating(true);

        try {
            const schemaConfig = getSchemaConfig();
            const response = await fetch('http://localhost:8000/jobs', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    schema_config: schemaConfig,
                    outcome_constraints: outcomeConstraints.map((c) => ({
                        ...c,
                        curve_points: c.curvePoints,
                    })),
                }),
            });

            if (response.ok) {
                const job = await response.json();
                setCurrentJobId(job.job_id);

                // Add to jobs list
                const newJob: Job = {
                    id: job.job_id,
                    status: 'PENDING',
                    progress: 0,
                    tables: tables.length,
                    rows: tables.reduce((acc, t) => acc + (t.rowCount || 100), 0),
                    createdAt: new Date().toISOString(),
                };
                setJobs((prev) => {
                    const updated = [newJob, ...prev];
                    localStorage.setItem('misata_jobs', JSON.stringify(updated));
                    return updated;
                });

                // Poll for completion
                let status = 'PENDING';
                let attempts = 0;
                while (status !== 'COMPLETE' && status !== 'ERROR' && attempts < 120) {
                    await new Promise((r) => setTimeout(r, 1000));
                    const statusRes = await fetch(`http://localhost:8000/jobs/${job.job_id}`);
                    if (statusRes.ok) {
                        const data = await statusRes.json();
                        status = data.status;
                        // Update job status
                        setJobs((prev) => {
                            const updated = prev.map((j) =>
                                j.id === job.job_id
                                    ? { ...j, status: status === 'COMPLETE' ? 'SUCCESS' : status, progress: data.progress || 0 }
                                    : j
                            );
                            localStorage.setItem('misata_jobs', JSON.stringify(updated));
                            return updated;
                        });
                    }
                    attempts++;
                }

                if (status === 'COMPLETE') {
                    // Fetch preview data
                    const dataRes = await fetch(`http://localhost:8000/jobs/${job.job_id}/data?limit=20`);
                    if (dataRes.ok) {
                        const data = await dataRes.json();
                        setPreviewData(data.tables || {});
                        if (tables[0]) {
                            setSelectedPreviewTable(tables[0].name);
                        }
                    }

                    // Fetch quality report
                    try {
                        const reportRes = await fetch(`http://localhost:8000/jobs/${job.job_id}/quality-report`);
                        if (reportRes.ok) {
                            const report = await reportRes.json();
                            setQualityReportData(report);
                        }
                    } catch { }
                }
            }
        } catch (e) {
            console.error('Generation failed', e);
        }

        setIsGenerating(false);
    };

    const handleStoryGenerate = async () => {
        if (!story.trim()) return;
        setIsGenerating(true);

        try {
            const response = await fetch('http://localhost:8000/studio/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ story }),
            });

            if (response.ok) {
                const { session_id } = await response.json();

                let attempts = 0;
                while (attempts < 60) {
                    await new Promise((r) => setTimeout(r, 500));
                    const statusRes = await fetch(`http://localhost:8000/studio/session/${session_id}`);
                    if (statusRes.ok) {
                        const session = await statusRes.json();
                        if (session.status === 'complete' && session.schema) {
                            clearSchema();

                            session.schema.tables.forEach((t: { name: string; row_count?: number }, i: number) => {
                                const columns = (session.schema.columns[t.name] || []).map(
                                    (c: { name: string; type: string }, j: number) => ({
                                        id: `col_${Date.now()}_${i}_${j}`,
                                        name: c.name,
                                        type: c.type as 'int' | 'text' | 'float' | 'date' | 'datetime' | 'boolean' | 'uuid' | 'email' | 'phone' | 'url' | 'json' | 'money',
                                    })
                                );
                                addTable({
                                    id: `table_${Date.now()}_${i}`,
                                    name: t.name,
                                    columns,
                                    rowCount: Math.min(t.row_count || 100, 500), // Cap at 500 for demo
                                    position: { x: 100 + (i % 3) * 300, y: 100 + Math.floor(i / 3) * 250 },
                                });
                            });

                            if (session.schema.relationships) {
                                session.schema.relationships.forEach(
                                    (
                                        r: {
                                            parent_table: string;
                                            child_table: string;
                                            parent_key: string;
                                            child_key: string;
                                        },
                                        i: number
                                    ) => {
                                        addRelationship({
                                            id: `rel_${Date.now()}_${i}`,
                                            parentTable: r.parent_table,
                                            childTable: r.child_table,
                                            parentKey: r.parent_key,
                                            childKey: r.child_key,
                                        });
                                    }
                                );
                            }

                            setShowStoryMode(false);
                            break;
                        }
                        if (session.status === 'error') break;
                    }
                    attempts++;
                }
            }
        } catch (e) {
            console.error('Story generation failed', e);
        }

        setIsGenerating(false);
    };

    const handleExport = async (format: 'csv' | 'json' | 'sql') => {
        if (!currentJobId) {
            alert('Generate data first');
            return;
        }

        try {
            const response = await fetch(`http://localhost:8000/jobs/${currentJobId}/export?format=${format}`);
            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `misata_data.${format === 'sql' ? 'sql' : format}`;
                a.click();
                window.URL.revokeObjectURL(url);
            }
        } catch (e) {
            console.error('Export failed', e);
        }
    };

    // Keyboard shortcuts
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.metaKey || e.ctrlKey) {
                if (e.key === 'z' && !e.shiftKey) {
                    e.preventDefault();
                    undo();
                }
                if (e.key === 'z' && e.shiftKey) {
                    e.preventDefault();
                    redo();
                }
                if (e.key === 'n') {
                    e.preventDefault();
                    handleAddTable();
                }
            }
            if (e.key === 'Delete' || e.key === 'Backspace') {
                if (selectedNode && !document.activeElement?.tagName?.match(/INPUT|TEXTAREA/)) {
                    removeTable(selectedNode);
                    setSelectedNode(null);
                }
            }
        };

        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [selectedNode, undo, redo, removeTable]);

    // Theme colors
    const colors = useMemo(
        () => ({
            bg: isDark ? '#1A1F16' : '#FAFAF8',
            surface: isDark ? '#252B21' : '#FFFFFF',
            border: isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)',
            text: isDark ? '#E8E6E0' : '#344E41',
            textMuted: isDark ? '#8B9185' : '#6B7164',
            accent: isDark ? '#A3B18A' : '#588157',
            accentBg: isDark ? 'rgba(163, 177, 138, 0.15)' : 'rgba(88, 129, 87, 0.1)',
        }),
        [isDark]
    );

    return (
        <ThemeContext.Provider value={{ isDark, toggle: toggleTheme }}>
            <div
                className="h-screen flex flex-col transition-colors duration-300"
                style={{ background: colors.bg }}
            >
                {/* Top Bar */}
                <header
                    className="h-14 flex items-center justify-between px-4 border-b transition-colors duration-300"
                    style={{ background: colors.surface, borderColor: colors.border }}
                >
                    <div className="flex items-center gap-4">
                        <div className="flex items-center gap-2">
                            <div
                                className="w-9 h-9 rounded-xl flex items-center justify-center shadow-sm"
                                style={{ background: 'linear-gradient(135deg, #3A5A40 0%, #588157 100%)' }}
                            >
                                <Database className="w-5 h-5 text-white" />
                            </div>
                            <div>
                                <span className="font-semibold text-lg" style={{ color: colors.text }}>
                                    MisataStudio
                                </span>
                                <span
                                    className="ml-2 text-xs px-2 py-0.5 rounded-full"
                                    style={{ background: colors.accentBg, color: colors.accent }}
                                >
                                    Beta
                                </span>
                            </div>
                        </div>

                        <div className="h-6 w-px" style={{ background: colors.border }} />

                        <div className="flex items-center gap-1">
                            <button
                                onClick={undo}
                                disabled={historyIndex <= 0}
                                className="p-2 rounded-lg hover:bg-black/5 dark:hover:bg-white/5 disabled:opacity-30 transition-all"
                                title="Undo (⌘Z)"
                            >
                                <Undo2 className="w-4 h-4" style={{ color: colors.textMuted }} />
                            </button>
                            <button
                                onClick={redo}
                                disabled={historyIndex >= history.length - 1}
                                className="p-2 rounded-lg hover:bg-black/5 dark:hover:bg-white/5 disabled:opacity-30 transition-all"
                                title="Redo (⌘⇧Z)"
                            >
                                <Redo2 className="w-4 h-4" style={{ color: colors.textMuted }} />
                            </button>
                        </div>
                    </div>

                    <div className="flex items-center gap-2">
                        {/* Theme Toggle */}
                        <button
                            onClick={toggleTheme}
                            className="p-2 rounded-lg hover:bg-black/5 dark:hover:bg-white/5 transition-all"
                            title={isDark ? 'Light Mode' : 'Dark Mode'}
                        >
                            {isDark ? (
                                <Sun className="w-4 h-4" style={{ color: colors.accent }} />
                            ) : (
                                <Moon className="w-4 h-4" style={{ color: colors.textMuted }} />
                            )}
                        </button>

                        {/* Jobs Button */}
                        <button
                            onClick={() => setShowJobsPanel(!showJobsPanel)}
                            className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-all hover:bg-black/5 dark:hover:bg-white/5"
                            style={{ color: colors.textMuted }}
                        >
                            <Activity className="w-4 h-4" />
                            Jobs
                            {jobs.filter((j) => j.status === 'PENDING' || j.status === 'PROGRESS').length > 0 && (
                                <span
                                    className="w-5 h-5 rounded-full text-xs flex items-center justify-center text-white"
                                    style={{ background: colors.accent }}
                                >
                                    {jobs.filter((j) => j.status === 'PENDING' || j.status === 'PROGRESS').length}
                                </span>
                            )}
                        </button>

                        {/* Quality Report Button */}
                        {qualityReportData && (
                            <button
                                onClick={() => setShowQualityReport(true)}
                                className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-all hover:bg-black/5 dark:hover:bg-white/5"
                                style={{ color: colors.accent }}
                            >
                                <BarChart3 className="w-4 h-4" />
                                Report
                            </button>
                        )}

                        {/* AI Story */}
                        <button
                            onClick={() => setShowStoryMode(true)}
                            className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-all hover:bg-black/5 dark:hover:bg-white/5"
                            style={{ color: colors.accent }}
                        >
                            <Sparkles className="w-4 h-4" />
                            AI Story
                        </button>

                        {/* Generate */}
                        <button
                            onClick={handleGenerate}
                            disabled={isGenerating || tables.length === 0}
                            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-white transition-all hover:opacity-90 disabled:opacity-50 shadow-sm"
                            style={{ background: 'linear-gradient(135deg, #588157 0%, #3A5A40 100%)' }}
                        >
                            {isGenerating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                            {isGenerating ? 'Generating...' : 'Generate'}
                        </button>

                        {/* Export */}
                        <div className="relative group">
                            <button
                                className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm border transition-all hover:bg-black/5 dark:hover:bg-white/5"
                                style={{ borderColor: colors.border, color: colors.text }}
                            >
                                <Download className="w-4 h-4" />
                                Export
                                <ChevronDown className="w-3 h-3" />
                            </button>
                            <div
                                className="absolute right-0 top-full mt-1 w-44 rounded-xl border shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50"
                                style={{ background: colors.surface, borderColor: colors.border }}
                            >
                                <div className="p-1">
                                    {[
                                        { format: 'csv', icon: FileSpreadsheet, color: '#10B981', label: 'CSV' },
                                        { format: 'json', icon: FileJson, color: '#F59E0B', label: 'JSON' },
                                        { format: 'sql', icon: Database, color: '#3B82F6', label: 'SQL' },
                                    ].map(({ format, icon: Icon, color, label }) => (
                                        <button
                                            key={format}
                                            onClick={() => handleExport(format as 'csv' | 'json' | 'sql')}
                                            className="w-full flex items-center gap-3 px-3 py-2.5 text-sm rounded-lg hover:bg-black/5 dark:hover:bg-white/5"
                                            style={{ color: colors.text }}
                                        >
                                            <Icon className="w-4 h-4" style={{ color }} />
                                            <span>{label}</span>
                                        </button>
                                    ))}
                                </div>
                            </div>
                        </div>
                    </div>
                </header>

                {/* Main Content */}
                <div className="flex-1 flex overflow-hidden">
                    {/* Canvas */}
                    <div className="flex-1 relative">
                        <ReactFlow
                            nodes={nodes}
                            edges={edges}
                            onNodesChange={onNodesChange}
                            onEdgesChange={onEdgesChange}
                            onConnect={onConnect}
                            onNodeClick={onNodeClick}
                            onNodeDragStop={onNodeDragStop}
                            nodeTypes={nodeTypes}
                            fitView
                            proOptions={{ hideAttribution: true }}
                        >
                            <Background color={isDark ? '#3A3F36' : '#E5E7EB'} gap={20} />
                            <Controls
                                className="rounded-lg shadow-lg border"
                                style={{ background: colors.surface, borderColor: colors.border }}
                            />
                            <MiniMap
                                nodeColor={colors.accent}
                                maskColor={isDark ? 'rgba(26,31,22,0.8)' : 'rgba(255,255,255,0.8)'}
                                className="rounded-lg shadow-lg border"
                                style={{ background: colors.surface, borderColor: colors.border }}
                            />

                            <Panel position="top-left" className="flex gap-2">
                                <button
                                    onClick={handleAddTable}
                                    className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium shadow-lg transition-all hover:shadow-xl animate-fade-in"
                                    style={{ background: colors.surface, color: colors.accent }}
                                >
                                    <Plus className="w-4 h-4" />
                                    Add Table
                                </button>
                            </Panel>

                            <Panel position="bottom-left" className="flex gap-3">
                                {[
                                    { icon: Layers, label: `${tables.length} tables` },
                                    { icon: Link2, label: `${relationships.length} relationships` },
                                    { icon: TrendingUp, label: `${outcomeConstraints.length} curves` },
                                ].map(({ icon: Icon, label }) => (
                                    <div
                                        key={label}
                                        className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs shadow-lg animate-slide-up"
                                        style={{ background: colors.surface }}
                                    >
                                        <Icon className="w-4 h-4" style={{ color: colors.accent }} />
                                        <span style={{ color: colors.text }}>{label}</span>
                                    </div>
                                ))}
                            </Panel>
                        </ReactFlow>

                        {/* Empty State */}
                        {tables.length === 0 && (
                            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                                <div className="text-center pointer-events-auto animate-fade-in">
                                    <div
                                        className="w-20 h-20 rounded-2xl flex items-center justify-center mx-auto mb-6 shadow-lg"
                                        style={{ background: colors.accentBg }}
                                    >
                                        <Database className="w-10 h-10" style={{ color: colors.accent }} />
                                    </div>
                                    <h2 className="text-2xl font-semibold mb-2" style={{ color: colors.text }}>
                                        Start Designing Your Data
                                    </h2>
                                    <p className="mb-8 max-w-md" style={{ color: colors.textMuted }}>
                                        Add tables manually or use AI to generate a complete schema
                                    </p>
                                    <div className="flex items-center justify-center gap-3">
                                        <button
                                            onClick={handleAddTable}
                                            className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium shadow-lg transition-all hover:shadow-xl"
                                            style={{
                                                background: colors.surface,
                                                color: colors.accent,
                                                border: `1px solid ${colors.border}`,
                                            }}
                                        >
                                            <Plus className="w-4 h-4" />
                                            Add Table
                                        </button>
                                        <button
                                            onClick={() => setShowStoryMode(true)}
                                            className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium text-white shadow-lg transition-all hover:shadow-xl"
                                            style={{ background: 'linear-gradient(135deg, #588157 0%, #3A5A40 100%)' }}
                                        >
                                            <Sparkles className="w-4 h-4" />
                                            AI Story
                                        </button>
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Properties Panel */}
                    <aside
                        className="w-72 border-l flex flex-col overflow-hidden transition-colors duration-300"
                        style={{ background: colors.surface, borderColor: colors.border }}
                    >
                        <div className="p-4 border-b" style={{ borderColor: colors.border }}>
                            <h3 className="font-semibold text-sm" style={{ color: colors.text }}>
                                Properties
                            </h3>
                        </div>

                        {selectedTable ? (
                            <div className="flex-1 overflow-auto animate-fade-in">
                                <div className="p-4 border-b" style={{ borderColor: colors.border }}>
                                    <div className="flex items-center gap-2 mb-3">
                                        <div
                                            className="w-8 h-8 rounded-lg flex items-center justify-center"
                                            style={{ background: colors.accentBg }}
                                        >
                                            <Layers className="w-4 h-4" style={{ color: colors.accent }} />
                                        </div>
                                        <input
                                            type="text"
                                            value={selectedTable.name}
                                            onChange={(e) => updateTable(selectedTable.id, { name: e.target.value })}
                                            className="flex-1 font-medium bg-transparent focus:outline-none px-2 py-1 rounded"
                                            style={{ color: colors.text }}
                                        />
                                    </div>
                                    <div className="flex items-center gap-2 text-xs" style={{ color: colors.textMuted }}>
                                        <Columns className="w-3 h-3" />
                                        <span>{selectedTable.columns.length} columns</span>
                                    </div>
                                </div>

                                <div className="p-4 border-b" style={{ borderColor: colors.border }}>
                                    <label
                                        className="text-xs font-medium uppercase tracking-wider mb-2 block"
                                        style={{ color: colors.textMuted }}
                                    >
                                        Row Count
                                    </label>
                                    <input
                                        type="number"
                                        value={selectedTable.rowCount || 100}
                                        onChange={(e) =>
                                            updateTable(selectedTable.id, { rowCount: parseInt(e.target.value) || 100 })
                                        }
                                        className="w-full px-3 py-2 rounded-lg border text-sm focus:outline-none transition-colors"
                                        style={{ borderColor: colors.border, color: colors.text, background: 'transparent' }}
                                    />
                                </div>

                                <div className="p-4 border-b" style={{ borderColor: colors.border }}>
                                    <label
                                        className="text-xs font-medium uppercase tracking-wider mb-3 block"
                                        style={{ color: colors.textMuted }}
                                    >
                                        Relationships
                                    </label>
                                    {relationships.filter(
                                        (r) => r.parentTable === selectedTable.name || r.childTable === selectedTable.name
                                    ).length > 0 ? (
                                        <div className="space-y-2">
                                            {relationships
                                                .filter(
                                                    (r) =>
                                                        r.parentTable === selectedTable.name ||
                                                        r.childTable === selectedTable.name
                                                )
                                                .map((rel) => (
                                                    <div
                                                        key={rel.id}
                                                        className="flex items-center justify-between px-3 py-2 rounded-lg animate-slide-up"
                                                        style={{ background: colors.accentBg }}
                                                    >
                                                        <div className="text-xs" style={{ color: colors.text }}>
                                                            <span className="font-medium">{rel.parentTable}</span>
                                                            <span style={{ color: colors.textMuted }}>.{rel.parentKey}</span>
                                                            <span className="mx-1">→</span>
                                                            <span className="font-medium">{rel.childTable}</span>
                                                            <span style={{ color: colors.textMuted }}>.{rel.childKey}</span>
                                                        </div>
                                                        <button
                                                            onClick={() => removeRelationship(rel.id)}
                                                            className="p-1 hover:bg-red-100 dark:hover:bg-red-900/30 rounded"
                                                        >
                                                            <Trash2 className="w-3 h-3 text-red-400" />
                                                        </button>
                                                    </div>
                                                ))}
                                        </div>
                                    ) : (
                                        <p className="text-xs" style={{ color: colors.textMuted }}>
                                            Drag from column handle to create relationships
                                        </p>
                                    )}
                                </div>

                                <div className="p-4">
                                    <label
                                        className="text-xs font-medium uppercase tracking-wider mb-3 block"
                                        style={{ color: colors.textMuted }}
                                    >
                                        Outcome Curves
                                    </label>
                                    {outcomeConstraints.filter((c) => c.tableId === selectedTable.id).length > 0 ? (
                                        <div className="space-y-2">
                                            {outcomeConstraints
                                                .filter((c) => c.tableId === selectedTable.id)
                                                .map((curve) => (
                                                    <div
                                                        key={curve.id}
                                                        className="flex items-center justify-between px-3 py-2 rounded-lg animate-slide-up"
                                                        style={{ background: 'rgba(245, 158, 11, 0.1)' }}
                                                    >
                                                        <div className="flex items-center gap-2">
                                                            <TrendingUp className="w-3 h-3" style={{ color: '#F59E0B' }} />
                                                            <span className="text-xs font-medium" style={{ color: colors.text }}>
                                                                {curve.columnName}
                                                            </span>
                                                        </div>
                                                        <span className="text-xs" style={{ color: colors.textMuted }}>
                                                            {curve.preset || 'Custom'}
                                                        </span>
                                                    </div>
                                                ))}
                                        </div>
                                    ) : (
                                        <p className="text-xs" style={{ color: colors.textMuted }}>
                                            Click numeric column to add curve
                                        </p>
                                    )}
                                </div>
                            </div>
                        ) : (
                            <div className="flex-1 flex items-center justify-center p-4">
                                <div className="text-center">
                                    <Settings2 className="w-8 h-8 mx-auto mb-2 opacity-20" />
                                    <p className="text-sm" style={{ color: colors.textMuted }}>
                                        Select a table
                                    </p>
                                </div>
                            </div>
                        )}

                        <div
                            className="p-4 border-t"
                            style={{ background: 'rgba(16, 185, 129, 0.05)', borderColor: colors.border }}
                        >
                            <div className="flex items-center gap-2">
                                <CheckCircle2 className="w-4 h-4" style={{ color: '#10B981' }} />
                                <span className="text-xs font-medium" style={{ color: '#10B981' }}>
                                    Schema Valid
                                </span>
                            </div>
                        </div>
                    </aside>

                    {/* Jobs Panel */}
                    {showJobsPanel && (
                        <aside
                            className="w-80 border-l flex flex-col overflow-hidden animate-slide-in-right"
                            style={{ background: colors.surface, borderColor: colors.border }}
                        >
                            <div className="p-4 border-b flex items-center justify-between" style={{ borderColor: colors.border }}>
                                <h3 className="font-semibold text-sm" style={{ color: colors.text }}>
                                    Jobs Queue
                                </h3>
                                <button onClick={() => setShowJobsPanel(false)} className="p-1 rounded hover:bg-black/5">
                                    <X className="w-4 h-4" style={{ color: colors.textMuted }} />
                                </button>
                            </div>
                            <div className="flex-1 overflow-auto">
                                {jobs.length === 0 ? (
                                    <div className="p-8 text-center">
                                        <Activity className="w-8 h-8 mx-auto mb-2 opacity-20" />
                                        <p className="text-sm" style={{ color: colors.textMuted }}>
                                            No jobs yet
                                        </p>
                                    </div>
                                ) : (
                                    <div className="p-2 space-y-2">
                                        {jobs.slice(0, 10).map((job) => (
                                            <div
                                                key={job.id}
                                                className="p-3 rounded-lg border animate-fade-in"
                                                style={{ borderColor: colors.border }}
                                            >
                                                <div className="flex items-center justify-between mb-2">
                                                    <span className="text-xs font-mono" style={{ color: colors.textMuted }}>
                                                        {job.id.slice(0, 8)}
                                                    </span>
                                                    <span
                                                        className={`text-xs px-2 py-0.5 rounded-full ${job.status === 'SUCCESS'
                                                                ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                                                                : job.status === 'FAILURE'
                                                                    ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                                                                    : 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400'
                                                            }`}
                                                    >
                                                        {job.status}
                                                    </span>
                                                </div>
                                                <div className="flex items-center gap-3 text-xs" style={{ color: colors.textMuted }}>
                                                    <span>{job.tables} tables</span>
                                                    <span>{job.rows.toLocaleString()} rows</span>
                                                </div>
                                                {(job.status === 'PENDING' || job.status === 'PROGRESS') && (
                                                    <div className="mt-2">
                                                        <div
                                                            className="h-1 rounded-full overflow-hidden"
                                                            style={{ background: colors.border }}
                                                        >
                                                            <div
                                                                className="h-full transition-all"
                                                                style={{
                                                                    background: colors.accent,
                                                                    width: `${job.progress}%`,
                                                                }}
                                                            />
                                                        </div>
                                                    </div>
                                                )}
                                                {job.status === 'SUCCESS' && (
                                                    <div className="mt-2 flex gap-2">
                                                        <button
                                                            onClick={() => {
                                                                setCurrentJobId(job.id);
                                                                setShowDataViewer(true);
                                                            }}
                                                            className="flex-1 flex items-center justify-center gap-1 px-2 py-1 rounded text-xs"
                                                            style={{ background: colors.accentBg, color: colors.accent }}
                                                        >
                                                            <Eye className="w-3 h-3" />
                                                            View
                                                        </button>
                                                        <button
                                                            onClick={async () => {
                                                                setCurrentJobId(job.id);
                                                                const res = await fetch(
                                                                    `http://localhost:8000/jobs/${job.id}/quality-report`
                                                                );
                                                                if (res.ok) {
                                                                    setQualityReportData(await res.json());
                                                                    setShowQualityReport(true);
                                                                }
                                                            }}
                                                            className="flex-1 flex items-center justify-center gap-1 px-2 py-1 rounded text-xs"
                                                            style={{ background: colors.accentBg, color: colors.accent }}
                                                        >
                                                            <BarChart3 className="w-3 h-3" />
                                                            Report
                                                        </button>
                                                    </div>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </aside>
                    )}
                </div>

                {/* Data Preview */}
                {Object.keys(previewData).length > 0 && (
                    <div
                        className="h-56 border-t flex flex-col transition-colors duration-300 animate-slide-up"
                        style={{ background: colors.surface, borderColor: colors.border }}
                    >
                        <div
                            className="flex items-center justify-between px-4 py-2 border-b"
                            style={{ borderColor: colors.border }}
                        >
                            <div className="flex items-center gap-4">
                                <span className="text-sm font-medium" style={{ color: colors.text }}>
                                    Data Preview
                                </span>
                                <div className="flex items-center gap-1">
                                    {Object.keys(previewData).map((tableName) => (
                                        <button
                                            key={tableName}
                                            onClick={() => setSelectedPreviewTable(tableName)}
                                            className={`px-3 py-1 rounded-lg text-xs transition-all ${selectedPreviewTable === tableName ? 'font-medium' : 'opacity-60 hover:opacity-100'
                                                }`}
                                            style={{
                                                background: selectedPreviewTable === tableName ? colors.accentBg : 'transparent',
                                                color: colors.text,
                                            }}
                                        >
                                            {tableName}
                                        </button>
                                    ))}
                                </div>
                            </div>
                            <button
                                onClick={() => setShowDataViewer(true)}
                                className="text-xs px-2 py-1 rounded hover:bg-black/5"
                                style={{ color: colors.accent }}
                            >
                                View All
                            </button>
                        </div>
                        <div className="flex-1 overflow-auto">
                            {selectedPreviewTable &&
                                previewData[selectedPreviewTable] &&
                                previewData[selectedPreviewTable].length > 0 ? (
                                <table className="w-full text-sm">
                                    <thead>
                                        <tr style={{ background: isDark ? '#1A1F16' : '#FAFAF8' }}>
                                            {Object.keys(previewData[selectedPreviewTable][0]).map((col) => (
                                                <th
                                                    key={col}
                                                    className="px-4 py-2 text-left font-medium text-xs uppercase tracking-wider sticky top-0"
                                                    style={{ color: colors.textMuted, background: isDark ? '#1A1F16' : '#FAFAF8' }}
                                                >
                                                    {col}
                                                </th>
                                            ))}
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {previewData[selectedPreviewTable].map((row, i) => (
                                            <tr key={i} className="border-t hover:bg-black/5" style={{ borderColor: colors.border }}>
                                                {Object.values(row).map((val, j) => (
                                                    <td key={j} className="px-4 py-2" style={{ color: colors.text }}>
                                                        {String(val).substring(0, 40)}
                                                        {String(val).length > 40 && '...'}
                                                    </td>
                                                ))}
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            ) : (
                                <div className="flex items-center justify-center h-full">
                                    <p className="text-sm" style={{ color: colors.textMuted }}>
                                        No preview data
                                    </p>
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {/* Modals */}
                {showStoryMode && (
                    <div className="fixed inset-0 z-50 flex items-center justify-center animate-fade-in" style={{ background: 'rgba(0,0,0,0.6)' }}>
                        <div className="w-[640px] rounded-2xl p-6 shadow-2xl animate-scale-in" style={{ background: colors.surface }}>
                            <div className="flex items-center justify-between mb-4">
                                <div className="flex items-center gap-3">
                                    <div
                                        className="w-10 h-10 rounded-xl flex items-center justify-center"
                                        style={{ background: 'linear-gradient(135deg, #588157 0%, #3A5A40 100%)' }}
                                    >
                                        <Sparkles className="w-5 h-5 text-white" />
                                    </div>
                                    <div>
                                        <h2 className="text-lg font-semibold" style={{ color: colors.text }}>
                                            Generate from Story
                                        </h2>
                                        <p className="text-xs" style={{ color: colors.textMuted }}>
                                            Describe your data scenario
                                        </p>
                                    </div>
                                </div>
                                <button onClick={() => setShowStoryMode(false)} className="p-2 hover:bg-black/5 rounded-lg">
                                    <X className="w-5 h-5" style={{ color: colors.textMuted }} />
                                </button>
                            </div>
                            <textarea
                                value={story}
                                onChange={(e) => setStory(e.target.value)}
                                placeholder="Example: An e-commerce platform with customers, orders, and products..."
                                className="w-full h-36 p-4 rounded-xl border resize-none text-sm focus:outline-none transition-colors"
                                style={{ borderColor: colors.border, color: colors.text, background: 'transparent' }}
                            />
                            <div className="flex justify-end gap-2 mt-4">
                                <button
                                    onClick={() => setShowStoryMode(false)}
                                    className="px-4 py-2 rounded-lg text-sm"
                                    style={{ color: colors.textMuted }}
                                >
                                    Cancel
                                </button>
                                <button
                                    onClick={handleStoryGenerate}
                                    disabled={isGenerating || !story.trim()}
                                    className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-medium text-white disabled:opacity-50 shadow-lg"
                                    style={{ background: 'linear-gradient(135deg, #588157 0%, #3A5A40 100%)' }}
                                >
                                    {isGenerating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                                    {isGenerating ? 'Generating...' : 'Generate Schema'}
                                </button>
                            </div>
                        </div>
                    </div>
                )}

                {showCurveEditor && curveEditorContext && (
                    <OutcomeCurveEditor
                        isOpen={showCurveEditor}
                        onClose={() => {
                            setShowCurveEditor(false);
                            setCurveEditorContext(null);
                        }}
                        tableId={curveEditorContext.tableId}
                        columnId={curveEditorContext.columnId}
                        tableName={curveEditorContext.tableName}
                        columnName={curveEditorContext.columnName}
                    />
                )}

                {showDataViewer && currentJobId && (
                    <DataViewer jobId={currentJobId} isOpen={showDataViewer} onClose={() => setShowDataViewer(false)} />
                )}

                {showQualityReport && qualityReportData && (
                    <QualityReport
                        report={qualityReportData as any}
                        isOpen={showQualityReport}
                        onClose={() => setShowQualityReport(false)}
                    />
                )}

                {/* CSS Animations */}
                <style jsx global>{`
                    @keyframes fadeIn {
                        from { opacity: 0; }
                        to { opacity: 1; }
                    }
                    @keyframes slideUp {
                        from { opacity: 0; transform: translateY(10px); }
                        to { opacity: 1; transform: translateY(0); }
                    }
                    @keyframes slideInRight {
                        from { opacity: 0; transform: translateX(20px); }
                        to { opacity: 1; transform: translateX(0); }
                    }
                    @keyframes scaleIn {
                        from { opacity: 0; transform: scale(0.95); }
                        to { opacity: 1; transform: scale(1); }
                    }
                    .animate-fade-in { animation: fadeIn 0.2s ease-out; }
                    .animate-slide-up { animation: slideUp 0.3s ease-out; }
                    .animate-slide-in-right { animation: slideInRight 0.3s ease-out; }
                    .animate-scale-in { animation: scaleIn 0.2s ease-out; }
                `}</style>
            </div>
        </ThemeContext.Provider>
    );
}

export default function Workspace() {
    return (
        <ReactFlowProvider>
            <WorkspaceContent />
        </ReactFlowProvider>
    );
}
