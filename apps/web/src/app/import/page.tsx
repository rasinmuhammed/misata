"use client";

import { useEffect, useState, Suspense, useCallback, useRef } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useSchemaStore, Column, TableNode } from '@/store/schemaStore';
import {
    Upload,
    FileJson,
    Check,
    AlertCircle,
    ArrowRight,
    Loader2,
    Download
} from 'lucide-react';

interface SchemaData {
    tables?: { name: string; row_count?: number }[];
    columns?: Record<string, { name: string; type: string; distribution_params?: Record<string, unknown> }[]>;
    relationships?: { parent_table: string; child_table: string; parent_key: string; child_key: string }[];
}

function ImportContent() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const { addTable, addRelationship, clearSchema } = useSchemaStore();
    const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
    const [error, setError] = useState<string | null>(null);
    const [schemaInfo, setSchemaInfo] = useState<{ tables: number; columns: number } | null>(null);
    const [isDragging, setIsDragging] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const importSchema = useCallback((schema: SchemaData) => {
        // Clear existing schema
        clearSchema();

        // Validate schema structure
        if (!schema.tables || !Array.isArray(schema.tables)) {
            throw new Error('Invalid schema format: missing tables array');
        }

        // Import tables
        const tableIdMap: Record<string, string> = {};

        schema.tables.forEach((tableData, index) => {
            const tableId = `table_${Date.now()}_${index}`;
            tableIdMap[tableData.name] = tableId;

            const columns: Column[] = (schema.columns?.[tableData.name] || []).map(
                (col, colIdx) => ({
                    id: `col_${Date.now()}_${index}_${colIdx}`,
                    name: col.name,
                    type: col.type as Column['type'],
                    distributionParams: col.distribution_params,
                })
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

        // Import relationships
        if (schema.relationships) {
            schema.relationships.forEach((rel, index) => {
                addRelationship({
                    id: `rel_${Date.now()}_${index}`,
                    sourceTable: tableIdMap[rel.parent_table] || rel.parent_table,
                    sourceColumn: rel.parent_key,
                    targetTable: tableIdMap[rel.child_table] || rel.child_table,
                    targetColumn: rel.child_key,
                });
            });
        }

        setSchemaInfo({
            tables: schema.tables.length,
            columns: Object.values(schema.columns || {}).flat().length,
        });
        setStatus('success');

        // Redirect to builder after delay
        setTimeout(() => {
            router.push('/builder');
        }, 1500);
    }, [addTable, addRelationship, clearSchema, router]);

    // Handle URL-based import
    useEffect(() => {
        const schemaParam = searchParams.get('schema');
        if (!schemaParam) return;

        setStatus('loading');
        try {
            const decoded = decodeURIComponent(escape(atob(schemaParam)));
            const schema = JSON.parse(decoded);
            importSchema(schema);
        } catch (err) {
            setStatus('error');
            setError(err instanceof Error ? err.message : 'Failed to import schema');
        }
    }, [searchParams, importSchema]);

    // Handle file upload
    const handleFile = useCallback((file: File) => {
        if (file.type !== 'application/json' && !file.name.endsWith('.json')) {
            setStatus('error');
            setError('Please upload a JSON file');
            return;
        }

        setStatus('loading');
        const reader = new FileReader();
        reader.onload = (e) => {
            try {
                const schema = JSON.parse(e.target?.result as string);
                importSchema(schema);
            } catch (err) {
                setStatus('error');
                setError(err instanceof Error ? err.message : 'Invalid JSON file');
            }
        };
        reader.onerror = () => {
            setStatus('error');
            setError('Failed to read file');
        };
        reader.readAsText(file);
    }, [importSchema]);

    // Drag and drop handlers
    const handleDragOver = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(true);
    }, []);

    const handleDragLeave = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(false);
    }, []);

    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(false);
        const file = e.dataTransfer.files[0];
        if (file) handleFile(file);
    }, [handleFile]);

    const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) handleFile(file);
    }, [handleFile]);

    return (
        <div className="min-h-screen flex items-center justify-center p-8 bg-[var(--bg-cosmos)]">
            <div className="card p-8 max-w-lg w-full">
                {status === 'idle' && (
                    <>
                        <div className="text-center mb-6">
                            <div className="w-16 h-16 mx-auto rounded-2xl bg-[var(--accent-aurora)]/20 flex items-center justify-center mb-4">
                                <Upload className="w-8 h-8 text-[var(--accent-aurora)]" />
                            </div>
                            <h1 className="text-xl font-bold text-[var(--text-primary)] mb-2">Import Schema</h1>
                            <p className="text-[var(--text-muted)] text-sm">
                                Upload a JSON schema file or paste a shared link
                            </p>
                        </div>

                        {/* Drag & Drop Zone */}
                        <div
                            onDragOver={handleDragOver}
                            onDragLeave={handleDragLeave}
                            onDrop={handleDrop}
                            onClick={() => fileInputRef.current?.click()}
                            className={`
                                border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all
                                ${isDragging
                                    ? 'border-[var(--accent-aurora)] bg-[var(--accent-aurora)]/10'
                                    : 'border-[var(--border-glass)] hover:border-[var(--accent-aurora)]/50 hover:bg-[var(--bg-nebula)]'
                                }
                            `}
                        >
                            <FileJson className={`w-12 h-12 mx-auto mb-4 ${isDragging ? 'text-[var(--accent-aurora)]' : 'text-[var(--text-muted)]'}`} />
                            <p className="text-[var(--text-secondary)] font-medium mb-1">
                                {isDragging ? 'Drop to import' : 'Drag & drop your schema.json'}
                            </p>
                            <p className="text-sm text-[var(--text-muted)]">
                                or click to browse
                            </p>
                        </div>

                        <input
                            ref={fileInputRef}
                            type="file"
                            accept=".json,application/json"
                            onChange={handleFileInput}
                            className="hidden"
                        />

                        <div className="flex items-center gap-4 my-6">
                            <div className="flex-1 h-px bg-[var(--border-glass)]" />
                            <span className="text-xs text-[var(--text-muted)]">or</span>
                            <div className="flex-1 h-px bg-[var(--border-glass)]" />
                        </div>

                        <button
                            onClick={() => router.push('/builder')}
                            className="btn btn-secondary w-full"
                        >
                            Start Fresh
                            <ArrowRight className="w-4 h-4" />
                        </button>
                    </>
                )}

                {status === 'loading' && (
                    <div className="text-center py-8">
                        <Loader2 className="w-12 h-12 mx-auto text-[var(--accent-aurora)] animate-spin mb-4" />
                        <h1 className="text-xl font-bold text-[var(--text-primary)] mb-2">Importing Schema</h1>
                        <p className="text-[var(--text-muted)]">Please wait...</p>
                    </div>
                )}

                {status === 'success' && (
                    <div className="text-center py-8">
                        <div className="w-16 h-16 mx-auto rounded-full bg-[var(--success)]/20 flex items-center justify-center mb-4">
                            <Check className="w-8 h-8 text-[var(--success)]" />
                        </div>
                        <h1 className="text-xl font-bold text-[var(--text-primary)] mb-2">Import Successful!</h1>
                        <p className="text-[var(--text-muted)] mb-4">
                            Imported {schemaInfo?.tables} tables with {schemaInfo?.columns} columns
                        </p>
                        <p className="text-sm text-[var(--accent-aurora)]">
                            Redirecting to Builder...
                        </p>
                    </div>
                )}

                {status === 'error' && (
                    <div className="text-center py-8">
                        <div className="w-16 h-16 mx-auto rounded-full bg-[var(--error)]/20 flex items-center justify-center mb-4">
                            <AlertCircle className="w-8 h-8 text-[var(--error)]" />
                        </div>
                        <h1 className="text-xl font-bold text-[var(--text-primary)] mb-2">Import Failed</h1>
                        <p className="text-[var(--error)] mb-6">{error}</p>
                        <div className="flex gap-3 justify-center">
                            <button
                                onClick={() => {
                                    setStatus('idle');
                                    setError(null);
                                }}
                                className="btn btn-secondary"
                            >
                                Try Again
                            </button>
                            <button
                                onClick={() => router.push('/builder')}
                                className="btn btn-primary"
                            >
                                Go to Builder
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

export default function ImportPage() {
    return (
        <Suspense fallback={
            <div className="min-h-screen flex items-center justify-center bg-[var(--bg-cosmos)]">
                <Loader2 className="w-8 h-8 text-[var(--accent-aurora)] animate-spin" />
            </div>
        }>
            <ImportContent />
        </Suspense>
    );
}

