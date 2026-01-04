"use client";

import { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { generateSchemaFromStory } from '@/lib/api';
import { useSchemaStore, Column, TableNode } from '@/store/schemaStore';
import {
    Sparkles,
    ShoppingCart,
    Briefcase,
    Users,
    Stethoscope,
    ArrowRight,
    Loader2,
    AlertCircle,
    CheckCircle,
    Table2,
    Columns3,
    GitBranch,
    RefreshCw,
    Wand2
} from 'lucide-react';

const examples = [
    {
        title: 'E-commerce Store',
        icon: ShoppingCart,
        color: 'aurora',
        story: 'A modern e-commerce platform with customers who can browse products, add items to cart, and place orders. Each order has multiple items and a shipping address. Products belong to categories and have reviews from customers.',
    },
    {
        title: 'SaaS Platform',
        icon: Briefcase,
        color: 'nebula',
        story: 'A B2B SaaS analytics platform where companies sign up with different subscription plans. Each company has multiple users with roles like admin, editor, and viewer. Users can create dashboards and add widgets with various metrics.',
    },
    {
        title: 'Social Network',
        icon: Users,
        color: 'cosmic',
        story: 'A social media app where users create profiles, post updates with text and images, follow other users, and like/comment on posts. Users can also create and join groups around shared interests.',
    },
    {
        title: 'Hospital System',
        icon: Stethoscope,
        color: 'celestial',
        story: 'A hospital management system tracking patients, doctors, appointments, and prescriptions. Doctors belong to departments and patients have medical history with diagnoses. Each appointment can result in prescriptions for medications.',
    },
];

const colorMap: Record<string, string> = {
    aurora: 'var(--accent-aurora)',
    nebula: 'var(--accent-nebula)',
    cosmic: 'var(--accent-cosmic)',
    celestial: 'var(--accent-celestial)',
};

interface GeneratedSchema {
    tables: Array<{ name: string; row_count: number }>;
    columns: Record<string, Array<{ name: string; type: string; distribution_params?: Record<string, unknown> }>>;
    relationships: Array<{ parent_table: string; child_table: string; parent_key: string; child_key: string }>;
    outcome_constraints?: Array<{
        table_name: string;
        column_name: string;
        curve_points: Array<{ timestamp: string; value: number }>;
        time_unit: string;
        avg_transaction_value?: number;
    }>;
}

export default function StoryPage() {
    const router = useRouter();
    const { addTable, addRelationship, addOrUpdateConstraint, setSchemaName, clearSchema } = useSchemaStore();

    const [datasetName, setDatasetName] = useState('');
    const [story, setStory] = useState('');
    const [isGenerating, setIsGenerating] = useState(false);
    const [generatedSchema, setGeneratedSchema] = useState<GeneratedSchema | null>(null);
    const [explanation, setExplanation] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [streamedText, setStreamedText] = useState('');

    const handleGenerate = useCallback(async () => {
        if (!story.trim()) return;

        setIsGenerating(true);
        setError(null);
        setGeneratedSchema(null);
        setStreamedText('');

        try {
            const result = await generateSchemaFromStory(
                story,
                (chunk) => {
                    setStreamedText(prev => prev + chunk);
                }
            );

            if (result.schema) {
                setGeneratedSchema(result.schema as GeneratedSchema);
                setExplanation(result.explanation || '');
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to generate schema');
        } finally {
            setIsGenerating(false);
        }
    }, [story]);

    const handleImportToBuilder = useCallback(() => {
        if (!generatedSchema) return;

        // Clear existing schema first
        clearSchema();

        const tableIdMap: Record<string, string> = {};
        const columnIdMap: Record<string, string> = {};

        generatedSchema.tables.forEach((tableData, index) => {
            const tableId = `table_${Date.now()}_${index}`;
            tableIdMap[tableData.name] = tableId;

            const columns: Column[] = (generatedSchema.columns[tableData.name] || []).map(
                (col, colIdx) => {
                    const colId = `col_${Date.now()}_${index}_${colIdx}`;
                    columnIdMap[`${tableData.name}.${col.name}`] = colId;

                    return {
                        id: colId,
                        name: col.name,
                        type: col.type as Column['type'],
                        distributionParams: col.distribution_params,
                    };
                }
            );

            const newTable: TableNode = {
                id: tableId,
                name: tableData.name,
                rowCount: tableData.row_count || 100,
                columns,
                position: {
                    x: 100 + (index % 3) * 350,
                    y: 100 + Math.floor(index / 3) * 300,
                },
            };

            addTable(newTable);
        });

        generatedSchema.relationships?.forEach((rel, index) => {
            addRelationship({
                id: `rel_${Date.now()}_${index}`,
                sourceTable: tableIdMap[rel.parent_table],
                sourceColumn: rel.parent_key,
                targetTable: tableIdMap[rel.child_table],
                targetColumn: rel.child_key,
            });
        });

        // Map Outcome Constraints (Metrics)
        generatedSchema.outcome_constraints?.forEach((oc, index) => {
            const tableId = tableIdMap[oc.table_name];
            const columnId = columnIdMap[`${oc.table_name}.${oc.column_name}`];

            if (tableId && columnId) {
                addOrUpdateConstraint({
                    id: `oc_${Date.now()}_${index}`,
                    tableId,
                    columnId,
                    curvePoints: oc.curve_points,
                    timeUnit: oc.time_unit as any,
                    avgTransactionValue: oc.avg_transaction_value
                });
            }
        });

        // Set Dataset Name
        setSchemaName(datasetName.trim() || 'Untitled Dataset');

        router.push('/builder');
    }, [generatedSchema, datasetName, addTable, addRelationship, addOrUpdateConstraint, setSchemaName, clearSchema, router]);

    return (
        <div className="p-8 max-w-4xl mx-auto animate-fade-in">
            {/* Header */}
            <div className="mb-8">
                <div className="flex items-center gap-3 mb-2">
                    <div className="w-10 h-10 rounded-lg bg-[var(--accent-aurora)]/20 flex items-center justify-center">
                        <Wand2 className="w-5 h-5 text-[var(--accent-aurora)]" />
                    </div>
                    <h1 className="text-heading text-[var(--text-primary)]">
                        Story Mode
                    </h1>
                </div>
                <p className="text-body text-[var(--text-muted)]">
                    Describe your data requirements in plain English. Our AI will generate a complete schema.
                </p>
            </div>

            {/* Examples */}
            <div className="mb-6">
                <p className="text-caption text-[var(--text-muted)] mb-3">Quick start with an example:</p>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {examples.map((example) => {
                        const Icon = example.icon;
                        const color = colorMap[example.color];
                        return (
                            <button
                                key={example.title}
                                onClick={() => setStory(example.story)}
                                className="card card-interactive p-4 text-left group"
                            >
                                <div
                                    className="w-8 h-8 rounded-lg flex items-center justify-center mb-2 transition-all group-hover:scale-110"
                                    style={{ backgroundColor: `${color}20` }}
                                >
                                    <Icon className="w-4 h-4 transition-colors" style={{ color }} />
                                </div>
                                <span className="text-sm font-medium text-[var(--text-secondary)] group-hover:text-[var(--text-primary)] transition-colors">
                                    {example.title}
                                </span>
                            </button>
                        );
                    })}
                </div>
            </div>

            {/* Input */}
            <div className="card p-6 mb-6">
                {/* Dataset Name Input */}
                <div className="mb-4">
                    <label className="block text-sm font-medium text-[var(--text-secondary)] mb-2">
                        Dataset Name <span className="text-[var(--text-muted)] font-normal">(optional)</span>
                    </label>
                    <input
                        type="text"
                        value={datasetName}
                        onChange={(e) => setDatasetName(e.target.value)}
                        placeholder="e.g., Marketing Analytics Q1"
                        className="input w-full"
                    />
                </div>

                <label className="block text-sm font-medium text-[var(--text-secondary)] mb-3">
                    Your Data Story
                </label>
                <textarea
                    value={story}
                    onChange={(e) => setStory(e.target.value)}
                    placeholder="Describe the data you need... e.g., 'An online food delivery app with restaurants, menus, customers, and orders...'"
                    className="input min-h-[160px] resize-none"
                    disabled={isGenerating}
                />
                <div className="flex items-center justify-between mt-4">
                    <p className="text-caption">
                        {story.length} / 2000 characters
                    </p>
                    <button
                        onClick={handleGenerate}
                        disabled={isGenerating || !story.trim()}
                        className="btn btn-primary"
                    >
                        {isGenerating ? (
                            <>
                                <Loader2 className="w-4 h-4 animate-spin" />
                                Generating...
                            </>
                        ) : (
                            <>
                                <Sparkles className="w-4 h-4" />
                                Generate Schema
                            </>
                        )}
                    </button>
                </div>
            </div>

            {/* Streaming Output */}
            {isGenerating && (
                <div className="card p-6 mb-6 border-[var(--accent-aurora)]/30">
                    <div className="flex items-center gap-2 mb-3">
                        <div className="w-2 h-2 rounded-full bg-[var(--accent-aurora)] animate-pulse" />
                        <span className="text-sm text-[var(--accent-aurora)]">AI is analyzing your story...</span>
                    </div>
                    <div className="bg-[var(--bg-nebula)] rounded-lg p-4 border border-[var(--border-glass)]">
                        <div className="flex items-center gap-3">
                            <Loader2 className="w-5 h-5 text-[var(--accent-aurora)] animate-spin" />
                            <div className="flex-1">
                                <div className="h-2 bg-[var(--accent-aurora)]/20 rounded-full overflow-hidden">
                                    <div className="h-full bg-[var(--accent-aurora)] rounded-full animate-pulse w-2/3" />
                                </div>
                            </div>
                        </div>
                        {streamedText && (
                            <p className="text-xs text-[var(--text-muted)] font-mono mt-3 truncate">
                                {streamedText.slice(-100)}
                            </p>
                        )}
                    </div>
                </div>
            )}

            {/* Error */}
            {error && (
                <div className="card p-6 mb-6 border-[var(--error)]/30 bg-[var(--error-muted)]">
                    <div className="flex items-center gap-2 text-[var(--error)]">
                        <AlertCircle className="w-4 h-4" />
                        <span className="font-medium">Generation Failed</span>
                    </div>
                    <p className="text-sm text-[var(--error)]/80 mt-2">{error}</p>
                </div>
            )}

            {/* Generated Schema */}
            {generatedSchema && !isGenerating && (
                <div className="card p-6 border-[var(--success)]/30">
                    <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-2 text-[var(--success)]">
                            <CheckCircle className="w-5 h-5" />
                            <span className="font-semibold">Schema Generated</span>
                        </div>
                        <div className="flex gap-2">
                            <button
                                onClick={handleGenerate}
                                className="btn btn-ghost btn-sm"
                                title="Regenerate"
                            >
                                <RefreshCw className="w-4 h-4" />
                            </button>
                            <button
                                onClick={handleImportToBuilder}
                                className="btn btn-primary btn-sm"
                            >
                                Import to Builder
                                <ArrowRight className="w-3.5 h-3.5" />
                            </button>
                        </div>
                    </div>

                    {explanation && (
                        <p className="text-sm text-[var(--text-secondary)] mb-4">{explanation}</p>
                    )}

                    {/* Stats */}
                    <div className="grid grid-cols-3 gap-4 mb-4">
                        <div className="bg-[var(--bg-nebula)] rounded-lg p-4 text-center border border-[var(--border-glass)]">
                            <div className="flex items-center justify-center gap-2 mb-1">
                                <Table2 className="w-4 h-4 text-[var(--accent-aurora)]" />
                                <span className="text-2xl font-bold text-[var(--text-primary)]">
                                    {generatedSchema.tables.length}
                                </span>
                            </div>
                            <p className="text-xs text-[var(--text-tertiary)]">Tables</p>
                        </div>
                        <div className="bg-[var(--bg-secondary)] rounded-lg p-4 text-center">
                            <div className="flex items-center justify-center gap-2 mb-1">
                                <Columns3 className="w-4 h-4 text-[var(--text-muted)]" />
                                <span className="text-2xl font-bold text-[var(--text-primary)]">
                                    {Object.values(generatedSchema.columns).flat().length}
                                </span>
                            </div>
                            <p className="text-xs text-[var(--text-tertiary)]">Columns</p>
                        </div>
                        <div className="bg-[var(--bg-secondary)] rounded-lg p-4 text-center">
                            <div className="flex items-center justify-center gap-2 mb-1">
                                <GitBranch className="w-4 h-4 text-[var(--text-muted)]" />
                                <span className="text-2xl font-bold text-[var(--text-primary)]">
                                    {generatedSchema.relationships?.length || 0}
                                </span>
                            </div>
                            <p className="text-xs text-[var(--text-tertiary)]">Relations</p>
                        </div>
                    </div>

                    {/* Table List */}
                    <div className="space-y-2">
                        {generatedSchema.tables.map((table) => (
                            <div key={table.name} className="bg-[var(--bg-secondary)] rounded-lg p-3">
                                <div className="flex items-center justify-between mb-2">
                                    <span className="font-medium text-[var(--text-primary)]">{table.name}</span>
                                    <span className="text-xs text-[var(--text-muted)]">{table.row_count} rows</span>
                                </div>
                                <div className="flex flex-wrap gap-1">
                                    {generatedSchema.columns[table.name]?.map((col) => (
                                        <span key={col.name} className="badge text-xs">
                                            {col.name}
                                            <span className="text-[var(--text-muted)] ml-1">({col.type})</span>
                                        </span>
                                    ))}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
