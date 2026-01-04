"use client";

import { useCallback, useMemo, useState, useEffect } from 'react';
import {
    ReactFlow,
    Background,
    Controls,
    MiniMap,
    useNodesState,
    useEdgesState,
    addEdge,
    Connection,
    Edge,
    Node,
    BackgroundVariant,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import TableNode from './TableNode';
import ShareModal from './ShareModal';
import { useKeyboardShortcuts, KeyboardShortcutsHelp } from './KeyboardShortcuts';
import { useSchemaStore } from '@/store/schemaStore';
import { submitJob, pollJobUntilComplete, downloadJobFiles, JobResponse } from '@/lib/api';
import { validateSchema, SchemaValidationResult } from '@/lib/validation';
import {
    Plus,
    Share2,
    Play,
    Loader2,
    CheckCircle,
    AlertCircle,
    AlertTriangle,
    X,
    FileText,
    Layers,
    Undo2,
    Redo2,
    Keyboard,
    Trash2,
    Download,
    BarChart3,
    ExternalLink
} from 'lucide-react';

const nodeTypes = {
    tableNode: TableNode,
};

export default function SchemaBuilder() {
    const { tables, relationships, addTable, updateTable, addRelationship, getSchemaConfig, undo, redo, clearSchema, history, historyIndex } = useSchemaStore();

    // Job state
    const [isGenerating, setIsGenerating] = useState(false);
    const [progress, setProgress] = useState(0);
    const [statusMessage, setStatusMessage] = useState('');
    const [result, setResult] = useState<JobResponse | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [currentJobId, setCurrentJobId] = useState<string | null>(null);
    const [showShareModal, setShowShareModal] = useState(false);

    // Convert tables to React Flow nodes
    const initialNodes: Node[] = useMemo(() =>
        tables.map((t) => ({
            id: t.id,
            type: 'tableNode',
            position: t.position,
            data: {
                label: t.name,
                rowCount: t.rowCount,
                columns: t.columns,
                tableId: t.id,
            },
        })),
        [tables]
    );

    // Convert relationships to edges
    const initialEdges: Edge[] = useMemo(() =>
        relationships.map((r) => {
            // Find the source and target tables
            const sourceTable = tables.find(t => t.id === r.sourceTable);
            const targetTable = tables.find(t => t.id === r.targetTable);

            // Find the actual column IDs - relationships may store column names OR column IDs
            // So we need to check both cases
            let sourceColumnId = r.sourceColumn;
            let targetColumnId = r.targetColumn;

            if (sourceTable) {
                // First check if sourceColumn is already a column ID
                const sourceColById = sourceTable.columns.find(c => c.id === r.sourceColumn);
                if (sourceColById) {
                    sourceColumnId = sourceColById.id;
                } else {
                    // Otherwise look up by column name
                    const sourceColByName = sourceTable.columns.find(c => c.name === r.sourceColumn);
                    if (sourceColByName) {
                        sourceColumnId = sourceColByName.id;
                    }
                }
            }

            if (targetTable) {
                // First check if targetColumn is already a column ID
                const targetColById = targetTable.columns.find(c => c.id === r.targetColumn);
                if (targetColById) {
                    targetColumnId = targetColById.id;
                } else {
                    // Otherwise look up by column name
                    const targetColByName = targetTable.columns.find(c => c.name === r.targetColumn);
                    if (targetColByName) {
                        targetColumnId = targetColByName.id;
                    }
                }
            }

            return {
                id: r.id,
                source: r.sourceTable,
                target: r.targetTable,
                sourceHandle: `${sourceColumnId}-source`,
                targetHandle: `${targetColumnId}-target`,
                animated: true,
                style: { stroke: 'var(--accent-aurora)', strokeWidth: 2 },
            };
        }),
        [relationships, tables]
    );

    const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

    const onConnect = useCallback(
        (connection: Connection) => {
            const newRel = {
                id: `rel_${Date.now()}`,
                sourceTable: connection.source || '',
                sourceColumn: connection.sourceHandle?.replace('-source', '') || '',
                targetTable: connection.target || '',
                targetColumn: connection.targetHandle?.replace('-target', '') || '',
            };
            addRelationship(newRel);
            setEdges((eds) => addEdge({
                ...connection,
                animated: true,
                style: { stroke: 'var(--brand-primary)', strokeWidth: 2 },
            }, eds));
        },
        [addRelationship, setEdges]
    );

    const onNodeDragStop = useCallback(
        (_: React.MouseEvent, node: Node) => {
            updateTable(node.id, { position: node.position });
        },
        [updateTable]
    );

    const handleAddTable = useCallback(() => {
        const newTable = {
            id: `table_${Date.now()}`,
            name: `new_table_${tables.length + 1}`,
            rowCount: 100,
            columns: [
                { id: `col_${Date.now()}`, name: 'id', type: 'int' as const },
            ],
            position: { x: 100 + tables.length * 50, y: 100 + tables.length * 50 },
        };
        addTable(newTable);

        setNodes((nds) => [
            ...nds,
            {
                id: newTable.id,
                type: 'tableNode',
                position: newTable.position,
                data: {
                    label: newTable.name,
                    rowCount: newTable.rowCount,
                    columns: newTable.columns,
                    tableId: newTable.id,
                },
            },
        ]);
    }, [tables.length, addTable, setNodes]);

    const handleGenerate = useCallback(async () => {
        if (tables.length === 0) {
            setError('Please add at least one table');
            return;
        }

        // Pre-generation schema validation
        const validationResult = validateSchema({
            tables: tables.map(t => ({
                id: t.id,
                name: t.name,
                rowCount: t.rowCount,
                columns: t.columns.map(c => ({
                    id: c.id,
                    name: c.name,
                    type: c.type,
                })),
            })),
        });

        if (!validationResult.isValid) {
            // Format the validation errors
            const errorMessages = validationResult.errors
                .map(e => `• ${e.path}: ${e.message}`)
                .join('\n');
            setError(`Schema validation failed:\n${errorMessages}`);
            return;
        }

        // Show warnings but proceed
        if (validationResult.warnings.length > 0) {
            console.warn('Schema validation warnings:', validationResult.warnings);
        }

        setIsGenerating(true);
        setProgress(0);
        setStatusMessage('Validating schema...');
        setError(null);
        setResult(null);

        // Small delay to show validation step
        await new Promise(resolve => setTimeout(resolve, 200));
        setStatusMessage('Submitting job...');

        try {
            const schemaConfig = getSchemaConfig();
            const jobResponse = await submitJob(schemaConfig as unknown as Parameters<typeof submitJob>[0]);

            // Save job to localStorage for Jobs dashboard
            const newJob = {
                id: jobResponse.job_id,
                status: 'PENDING' as const,
                progress: 0,
                schemaName: (schemaConfig as { name?: string }).name || 'Generated Schema',
                tables: tables.length,
                rows: tables.reduce((acc, t) => acc + t.rowCount, 0),
                createdAt: new Date().toISOString(),
            };

            const existingJobs = JSON.parse(localStorage.getItem('misata_jobs') || '[]');
            localStorage.setItem('misata_jobs', JSON.stringify([newJob, ...existingJobs]));

            setCurrentJobId(jobResponse.job_id);
            setStatusMessage(`Job ${jobResponse.job_id.slice(0, 8)}... queued`);

            const finalResult = await pollJobUntilComplete(
                jobResponse.job_id,
                (prog, msg) => {
                    setProgress(prog);
                    setStatusMessage(msg);

                    // Update job in localStorage
                    const jobs = JSON.parse(localStorage.getItem('misata_jobs') || '[]');
                    const updatedJobs = jobs.map((j: { id: string }) =>
                        j.id === jobResponse.job_id
                            ? { ...j, status: 'PROGRESS', progress: prog }
                            : j
                    );
                    localStorage.setItem('misata_jobs', JSON.stringify(updatedJobs));
                }
            );

            // Update job as completed
            const jobs = JSON.parse(localStorage.getItem('misata_jobs') || '[]');
            const completedJobs = jobs.map((j: { id: string }) =>
                j.id === jobResponse.job_id
                    ? { ...j, status: 'SUCCESS', progress: 100, files: finalResult.files }
                    : j
            );
            localStorage.setItem('misata_jobs', JSON.stringify(completedJobs));

            setResult(finalResult);
            setStatusMessage('Complete!');
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Unknown error');
        } finally {
            setIsGenerating(false);
        }
    }, [tables, getSchemaConfig]);

    // Download completed job files
    const handleDownload = useCallback(async () => {
        if (!currentJobId) return;

        try {
            const blob = await downloadJobFiles(currentJobId);
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `misata_${currentJobId.slice(0, 8)}.zip`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (err) {
            setError(`Download failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
        }
    }, [currentJobId]);

    // Keyboard shortcuts
    const { showHelp, setShowHelp } = useKeyboardShortcuts({
        onAddTable: handleAddTable,
        onGenerate: handleGenerate,
        onShare: () => setShowShareModal(true),
        onUndo: undo,
        onRedo: redo,
        onClear: clearSchema,
    });

    const canUndo = historyIndex > 0;
    const canRedo = historyIndex < history.length - 1;

    return (
        <div className="h-screen flex flex-col" style={{ background: '#DAD7CD' }}>
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b" style={{ borderColor: 'rgba(58, 90, 64, 0.15)', background: '#F5F3EF' }}>
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: 'rgba(88, 129, 87, 0.15)' }}>
                        <Layers className="w-5 h-5" style={{ color: '#3A5A40' }} />
                    </div>
                    <div>
                        <h1 className="text-xl font-medium" style={{ color: '#3A5A40', fontFamily: 'Cormorant Garamond, serif' }}>Schema Builder</h1>
                        <p className="text-xs" style={{ color: '#6B7164' }}>
                            {tables.length} tables • {tables.reduce((acc, t) => acc + t.columns.length, 0)} columns
                        </p>
                    </div>
                </div>
                <div className="flex gap-2">
                    {/* Undo/Redo */}
                    <button
                        onClick={undo}
                        disabled={!canUndo}
                        className="btn btn-ghost btn-sm"
                        title="Undo (⌘Z)"
                    >
                        <Undo2 className="w-4 h-4" />
                    </button>
                    <button
                        onClick={redo}
                        disabled={!canRedo}
                        className="btn btn-ghost btn-sm"
                        title="Redo (⌘⇧Z)"
                    >
                        <Redo2 className="w-4 h-4" />
                    </button>
                    <div className="w-px bg-[var(--border-glass)] mx-1" />
                    <button
                        onClick={() => setShowHelp(true)}
                        className="btn btn-ghost btn-sm"
                        title="Keyboard shortcuts (?)"
                    >
                        <Keyboard className="w-4 h-4" />
                    </button>
                    {tables.length > 0 && (
                        <button
                            onClick={() => {
                                if (confirm('Clear all tables?')) clearSchema();
                            }}
                            className="btn btn-ghost btn-sm text-[var(--error)]"
                            title="Clear all"
                        >
                            <Trash2 className="w-4 h-4" />
                        </button>
                    )}
                    <div className="w-px bg-[var(--border-glass)] mx-1" />
                    <button
                        onClick={handleAddTable}
                        className="btn btn-secondary btn-sm"
                    >
                        <Plus className="w-4 h-4" />
                        Add Table
                    </button>
                    <button
                        onClick={() => setShowShareModal(true)}
                        disabled={tables.length === 0}
                        className="btn btn-secondary btn-sm"
                    >
                        <Share2 className="w-4 h-4" />
                        Share
                    </button>
                    <button
                        onClick={handleGenerate}
                        disabled={isGenerating || tables.length === 0}
                        className="btn btn-primary btn-sm"
                    >
                        {isGenerating ? (
                            <>
                                <Loader2 className="w-4 h-4 animate-spin" />
                                {progress}%
                            </>
                        ) : (
                            <>
                                <Play className="w-4 h-4" />
                                Generate
                            </>
                        )}
                    </button>
                </div>
            </div>

            {/* Canvas */}
            <div className="flex-1 relative">
                {/* Status Panel */}
                {(isGenerating || result || error) && (
                    <div className="absolute top-4 right-4 z-10 w-80 card card-elevated p-4 animate-fade-in">
                        <div className="flex items-center justify-between mb-3">
                            <h3 className="text-sm font-medium text-[var(--text-primary)]">Generation Status</h3>
                            {!isGenerating && (
                                <button
                                    onClick={() => { setResult(null); setError(null); }}
                                    className="btn btn-ghost btn-sm p-1"
                                >
                                    <X className="w-3.5 h-3.5" />
                                </button>
                            )}
                        </div>

                        {isGenerating && (
                            <div className="space-y-2">
                                <div className="w-full bg-[var(--bg-secondary)] rounded-full h-1.5 overflow-hidden">
                                    <div
                                        className="bg-[var(--brand-primary)] h-1.5 transition-all"
                                        style={{ width: `${progress}%` }}
                                    />
                                </div>
                                <p className="text-xs text-[var(--text-muted)]">{statusMessage}</p>
                            </div>
                        )}

                        {error && (
                            <div className="flex items-start gap-2 p-3 bg-[var(--error-muted)] border border-[var(--error)]/30 rounded-lg">
                                <AlertCircle className="w-4 h-4 text-[var(--error)] flex-shrink-0 mt-0.5" />
                                <p className="text-xs text-[var(--error)]">{error}</p>
                            </div>
                        )}

                        {result && !isGenerating && (
                            <div className="space-y-3">
                                <div className="flex items-center gap-2 text-[var(--success)]">
                                    <CheckCircle className="w-5 h-5" />
                                    <span className="text-sm font-semibold">Generation Complete!</span>
                                </div>

                                {/* Job Info */}
                                <div className="bg-[var(--bg-nebula)] rounded-lg p-3 border border-[var(--border-glass)]">
                                    <div className="flex items-center justify-between mb-2">
                                        <span className="text-xs text-[var(--text-muted)]">Job ID</span>
                                        <span className="text-xs font-mono text-[var(--text-secondary)]">
                                            {currentJobId?.slice(0, 8)}...
                                        </span>
                                    </div>
                                    <div className="flex items-center justify-between">
                                        <span className="text-xs text-[var(--text-muted)]">Tables Generated</span>
                                        <span className="text-xs font-medium text-[var(--text-secondary)]">
                                            {tables.length} tables
                                        </span>
                                    </div>
                                </div>

                                {/* Action Buttons */}
                                <div className="flex gap-2">
                                    <button
                                        onClick={handleDownload}
                                        className="btn btn-primary flex-1"
                                    >
                                        <Download className="w-4 h-4" />
                                        Download ZIP
                                    </button>
                                </div>

                                <a
                                    href="/jobs"
                                    className="flex items-center justify-center gap-2 text-xs text-[var(--accent-aurora)] hover:underline"
                                >
                                    <BarChart3 className="w-3.5 h-3.5" />
                                    View in Jobs Dashboard
                                    <ExternalLink className="w-3 h-3" />
                                </a>
                            </div>
                        )}
                    </div>
                )}

                {/* Empty State */}
                {tables.length === 0 && (
                    <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-10">
                        <div className="text-center">
                            <Layers className="w-16 h-16 text-[var(--text-muted)] mx-auto mb-4 opacity-20" />
                            <h3 className="text-lg font-medium text-[var(--text-secondary)] mb-2">No tables yet</h3>
                            <p className="text-sm text-[var(--text-muted)]">Click "Add Table" to get started</p>
                        </div>
                    </div>
                )}

                <ReactFlow
                    nodes={nodes}
                    edges={edges}
                    onNodesChange={onNodesChange}
                    onEdgesChange={onEdgesChange}
                    onConnect={onConnect}
                    onNodeDragStop={onNodeDragStop}
                    nodeTypes={nodeTypes}
                    fitView
                    style={{ background: '#DAD7CD' }}
                    proOptions={{ hideAttribution: true }}
                >
                    <Background
                        variant={BackgroundVariant.Dots}
                        gap={24}
                        size={1}
                        color="rgba(58, 90, 64, 0.08)"
                    />
                    <Controls
                        className="!rounded-lg !shadow-md !bottom-4 !left-4"
                        style={{
                            background: '#FEFEFE',
                            border: '1px solid rgba(58, 90, 64, 0.15)'
                        }}
                        showInteractive={false}
                    />
                    {/* MiniMap - positioned bottom right */}
                    <MiniMap
                        className="!rounded-lg !shadow-md !bottom-4 !right-4 !top-auto !left-auto"
                        style={{
                            background: '#F5F3EF',
                            border: '1px solid rgba(58, 90, 64, 0.15)',
                            width: 120,
                            height: 80
                        }}
                        nodeColor="#588157"
                        maskColor="rgba(218, 215, 205, 0.85)"
                        zoomable
                        pannable
                    />
                </ReactFlow>
            </div>

            {/* Share Modal */}
            <ShareModal
                isOpen={showShareModal}
                onClose={() => setShowShareModal(false)}
            />

            {/* Keyboard Shortcuts Help */}
            <KeyboardShortcutsHelp
                isOpen={showHelp}
                onClose={() => setShowHelp(false)}
            />
        </div>
    );
}

