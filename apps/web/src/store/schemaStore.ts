"use client";

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface Column {
    id: string;
    name: string;
    type: 'int' | 'float' | 'text' | 'date' | 'time' | 'datetime' | 'categorical' | 'boolean' | 'foreign_key';
    distributionParams?: Record<string, unknown>;
}

export interface TableNode {
    id: string;
    name: string;
    rowCount: number;
    columns: Column[];
    position: { x: number; y: number };
}

export interface Relationship {
    id: string;
    sourceTable: string;
    sourceColumn: string;
    targetTable: string;
    targetColumn: string;
}

// MOONSHOT: Outcome Constraint
export interface CurvePoint {
    timestamp: string; // ISO date string for the period
    value: number;     // Target value for this period
}

export interface OutcomeConstraint {
    id: string;
    tableId: string;
    columnId: string;
    curvePoints: CurvePoint[];
    timeUnit: 'day' | 'week' | 'month' | 'quarter' | 'year';
    avgTransactionValue?: number;
    patternType?: string; // 'seasonal', 'growth', 'trend', etc.
    description?: string; // Human-readable description from LLM
}

interface SchemaSnapshot {
    tables: TableNode[];
    relationships: Relationship[];
}

interface SchemaState {
    tables: TableNode[];
    relationships: Relationship[];
    selectedTableId: string | null;

    // MOONSHOT: Outcome Constraints
    outcomeConstraints: OutcomeConstraint[];
    activeConstraintColumnId: string | null; // Currently editing constraint

    // History for undo/redo
    history: SchemaSnapshot[];
    historyIndex: number;

    // Metadata
    schemaName: string;
    setSchemaName: (name: string) => void;

    // Actions
    addTable: (table: TableNode) => void;
    updateTable: (id: string, updates: Partial<TableNode>) => void;
    removeTable: (id: string) => void;
    addColumn: (tableId: string, column: Column) => void;
    updateColumn: (tableId: string, columnId: string, updates: Partial<Column>) => void;
    removeColumn: (tableId: string, columnId: string) => void;
    setSelectedTable: (id: string | null) => void;
    addRelationship: (rel: Relationship) => void;
    removeRelationship: (id: string) => void;
    getSchemaConfig: () => Record<string, unknown>;

    // MOONSHOT: Constraint Actions
    setActiveConstraintColumn: (columnId: string | null) => void;
    addOrUpdateConstraint: (constraint: OutcomeConstraint) => void;
    removeConstraint: (constraintId: string) => void;
    getConstraintForColumn: (columnId: string) => OutcomeConstraint | undefined;

    // New actions for functionality
    clearSchema: () => void;
    loadSchema: (tables: TableNode[], relationships: Relationship[]) => void;
    undo: () => void;
    redo: () => void;
    saveToHistory: () => void;
}

const MAX_HISTORY = 50;

export const useSchemaStore = create<SchemaState>()(
    persist(
        (set, get) => ({
            tables: [],
            relationships: [],
            selectedTableId: null,
            outcomeConstraints: [],
            activeConstraintColumnId: null,
            history: [],
            historyIndex: -1,
            schemaName: 'Generated Schema',

            setSchemaName: (name) => set({ schemaName: name }),

            saveToHistory: () => set((state) => {
                const snapshot: SchemaSnapshot = {
                    tables: JSON.parse(JSON.stringify(state.tables)),
                    relationships: JSON.parse(JSON.stringify(state.relationships)),
                };
                const newHistory = state.history.slice(0, state.historyIndex + 1);
                newHistory.push(snapshot);
                if (newHistory.length > MAX_HISTORY) {
                    newHistory.shift();
                }
                return {
                    history: newHistory,
                    historyIndex: newHistory.length - 1,
                };
            }),

            undo: () => set((state) => {
                if (state.historyIndex <= 0) return state;
                const prevIndex = state.historyIndex - 1;
                const snapshot = state.history[prevIndex];
                return {
                    tables: snapshot.tables,
                    relationships: snapshot.relationships,
                    historyIndex: prevIndex,
                };
            }),

            redo: () => set((state) => {
                if (state.historyIndex >= state.history.length - 1) return state;
                const nextIndex = state.historyIndex + 1;
                const snapshot = state.history[nextIndex];
                return {
                    tables: snapshot.tables,
                    relationships: snapshot.relationships,
                    historyIndex: nextIndex,
                };
            }),

            addTable: (table) => {
                get().saveToHistory();
                set((state) => ({
                    tables: [...state.tables, table]
                }));
            },

            updateTable: (id, updates) => set((state) => ({
                tables: state.tables.map((t) =>
                    t.id === id ? { ...t, ...updates } : t
                ),
            })),

            removeTable: (id) => {
                get().saveToHistory();
                set((state) => ({
                    tables: state.tables.filter((t) => t.id !== id),
                    relationships: state.relationships.filter(
                        (r) => r.sourceTable !== id && r.targetTable !== id
                    ),
                }));
            },

            addColumn: (tableId, column) => {
                get().saveToHistory();
                set((state) => ({
                    tables: state.tables.map((t) =>
                        t.id === tableId ? { ...t, columns: [...t.columns, column] } : t
                    ),
                }));
            },

            updateColumn: (tableId, columnId, updates) => set((state) => ({
                tables: state.tables.map((t) =>
                    t.id === tableId
                        ? {
                            ...t,
                            columns: t.columns.map((c) =>
                                c.id === columnId ? { ...c, ...updates } : c
                            ),
                        }
                        : t
                ),
            })),

            removeColumn: (tableId, columnId) => {
                get().saveToHistory();
                set((state) => ({
                    tables: state.tables.map((t) =>
                        t.id === tableId
                            ? { ...t, columns: t.columns.filter((c) => c.id !== columnId) }
                            : t
                    ),
                }));
            },

            setSelectedTable: (id) => set({ selectedTableId: id }),

            addRelationship: (rel) => {
                get().saveToHistory();
                set((state) => ({
                    relationships: [...state.relationships, rel],
                }));
            },

            removeRelationship: (id) => {
                get().saveToHistory();
                set((state) => ({
                    relationships: state.relationships.filter((r) => r.id !== id),
                }));
            },

            clearSchema: () => {
                get().saveToHistory();
                set({
                    tables: [],
                    relationships: [],
                    outcomeConstraints: [],
                    selectedTableId: null,
                    schemaName: 'Generated Schema',
                });
            },

            loadSchema: (tables, relationships) => {
                get().saveToHistory();
                set({
                    tables,
                    relationships,
                    selectedTableId: null,
                });
            },

            // Export to SchemaConfig format for API
            getSchemaConfig: () => {
                const { tables, relationships, outcomeConstraints } = get();

                return {
                    name: get().schemaName,
                    tables: tables.map((t) => ({
                        name: t.name,
                        row_count: t.rowCount,
                    })),
                    columns: tables.reduce((acc, t) => {
                        acc[t.name] = t.columns.map((c) => ({
                            name: c.name,
                            type: c.type,
                            distribution_params: c.distributionParams || {},
                        }));
                        return acc;
                    }, {} as Record<string, unknown[]>),
                    relationships: relationships.map((r) => {
                        const sourceTable = tables.find((t) => t.id === r.sourceTable);
                        const targetTable = tables.find((t) => t.id === r.targetTable);
                        return {
                            parent_table: sourceTable?.name || r.sourceTable,
                            child_table: targetTable?.name || r.targetTable,
                            parent_key: r.sourceColumn,
                            child_key: r.targetColumn,
                        };
                    }),
                    // MOONSHOT: Include outcome constraints in the API payload
                    outcome_constraints: outcomeConstraints.map((oc) => {
                        const table = tables.find((t) => t.id === oc.tableId);
                        const column = table?.columns.find((c) => c.id === oc.columnId);
                        return {
                            table_name: table?.name || oc.tableId,
                            column_name: column?.name || oc.columnId,
                            curve_points: oc.curvePoints,
                            time_unit: oc.timeUnit,
                            avg_transaction_value: oc.avgTransactionValue,
                        };
                    }),
                    // Also include as outcome_curves format for LLM-style constraints
                    outcome_curves: outcomeConstraints.map((oc) => {
                        const table = tables.find((t) => t.id === oc.tableId);
                        const column = table?.columns.find((c) => c.id === oc.columnId);
                        // Find a date column in the same table
                        const dateCol = table?.columns.find((c) => c.type === 'date');
                        return {
                            table: table?.name || oc.tableId,
                            column: column?.name || oc.columnId,
                            time_column: dateCol?.name || 'date',
                            pattern_type: oc.patternType || 'seasonal',
                            description: oc.description || 'User-defined constraint',
                            curve_points: oc.curvePoints.map(p => ({
                                month: new Date(p.timestamp).getMonth() + 1,
                                relative_value: p.value / 10000 // Normalize back to 0-1
                            }))
                        };
                    }),
                };
            },

            // MOONSHOT: Constraint Actions
            setActiveConstraintColumn: (columnId) => set({ activeConstraintColumnId: columnId }),

            addOrUpdateConstraint: (constraint) => set((state) => {
                const existingIndex = state.outcomeConstraints.findIndex(c => c.id === constraint.id);
                if (existingIndex >= 0) {
                    const updated = [...state.outcomeConstraints];
                    updated[existingIndex] = constraint;
                    return { outcomeConstraints: updated };
                }
                return { outcomeConstraints: [...state.outcomeConstraints, constraint] };
            }),

            removeConstraint: (constraintId) => set((state) => ({
                outcomeConstraints: state.outcomeConstraints.filter(c => c.id !== constraintId),
            })),

            getConstraintForColumn: (columnId) => {
                return get().outcomeConstraints.find(c => c.columnId === columnId);
            },
        }),
        {
            name: 'misata-schema',
            partialize: (state) => ({
                tables: state.tables,
                relationships: state.relationships,
                outcomeConstraints: state.outcomeConstraints,
                schemaName: state.schemaName,
            }),
        }
    )
);

