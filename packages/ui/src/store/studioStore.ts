/**
 * MisataStudio Unified State Store
 * 
 * Central state management following Linear/Figma patterns:
 * - Single source of truth for all UI state
 * - Agents read/write to shared state
 * - Optimistic updates with background sync
 */

import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';

// Types
export interface Table {
    name: string;
    rowCount: number;
    columns: Column[];
}

export interface Column {
    name: string;
    type: string;
    distributionParams?: Record<string, unknown>;
}

export interface Relationship {
    parentTable: string;
    childTable: string;
    parentKey: string;
    childKey: string;
}

export interface OutcomeConstraint {
    metricName: string;
    factTable: string;
    valueColumn: string;
    dateColumn: string;
    curvePoints: { month: number; value: number }[];
}

export interface Job {
    id: string;
    status: 'pending' | 'running' | 'success' | 'failed';
    progress: number;
    createdAt: string;
    completedAt?: string;
    error?: string;
}

export interface ValidationResult {
    tableName: string;
    passed: boolean;
    complianceRate: number;
    violations: { rule: string; count: number }[];
}

export interface AgentMessage {
    role: 'user' | 'agent' | 'system';
    content: string;
    timestamp: string;
    agentName?: string;
}

// State Interface
export interface StudioState {
    // Workspace
    activePanel: 'story' | 'schema' | 'preview' | 'jobs' | 'validation';
    setActivePanel: (panel: StudioState['activePanel']) => void;

    // Story
    story: string;
    setStory: (story: string) => void;

    // Schema
    tables: Table[];
    relationships: Relationship[];
    outcomeConstraints: OutcomeConstraint[];
    setSchema: (tables: Table[], relationships: Relationship[], constraints: OutcomeConstraint[]) => void;
    addTable: (table: Table) => void;
    updateTable: (name: string, updates: Partial<Table>) => void;
    removeTable: (name: string) => void;

    // Generation
    jobs: Job[];
    activeJobId: string | null;
    addJob: (job: Job) => void;
    updateJob: (id: string, updates: Partial<Job>) => void;
    setActiveJob: (id: string | null) => void;

    // Data
    generatedData: Record<string, unknown[]>;
    setGeneratedData: (tableName: string, data: unknown[]) => void;
    clearGeneratedData: () => void;

    // Validation
    validationResults: ValidationResult[];
    overallComplianceRate: number;
    setValidationResults: (results: ValidationResult[]) => void;

    // Agent Context
    agentSessionId: string | null;
    agentMessages: AgentMessage[];
    agentStatus: 'idle' | 'thinking' | 'generating' | 'validating';
    setAgentStatus: (status: StudioState['agentStatus']) => void;
    addAgentMessage: (message: AgentMessage) => void;
    clearAgentSession: () => void;
}

// Store Implementation
export const useStudioStore = create<StudioState>()(
    devtools(
        persist(
            (set, get) => ({
                // Workspace
                activePanel: 'story',
                setActivePanel: (panel) => set({ activePanel: panel }),

                // Story
                story: '',
                setStory: (story) => set({ story }),

                // Schema
                tables: [],
                relationships: [],
                outcomeConstraints: [],
                setSchema: (tables, relationships, outcomeConstraints) =>
                    set({ tables, relationships, outcomeConstraints }),
                addTable: (table) => set((state) => ({ tables: [...state.tables, table] })),
                updateTable: (name, updates) => set((state) => ({
                    tables: state.tables.map((t) =>
                        t.name === name ? { ...t, ...updates } : t
                    ),
                })),
                removeTable: (name) => set((state) => ({
                    tables: state.tables.filter((t) => t.name !== name),
                    relationships: state.relationships.filter(
                        (r) => r.parentTable !== name && r.childTable !== name
                    ),
                })),

                // Generation
                jobs: [],
                activeJobId: null,
                addJob: (job) => set((state) => ({ jobs: [...state.jobs, job] })),
                updateJob: (id, updates) => set((state) => ({
                    jobs: state.jobs.map((j) => (j.id === id ? { ...j, ...updates } : j)),
                })),
                setActiveJob: (id) => set({ activeJobId: id }),

                // Data
                generatedData: {},
                setGeneratedData: (tableName, data) => set((state) => ({
                    generatedData: { ...state.generatedData, [tableName]: data },
                })),
                clearGeneratedData: () => set({ generatedData: {} }),

                // Validation
                validationResults: [],
                overallComplianceRate: 0,
                setValidationResults: (results) => {
                    const totalRate = results.reduce((sum, r) => sum + r.complianceRate, 0) / results.length;
                    set({ validationResults: results, overallComplianceRate: totalRate || 0 });
                },

                // Agent Context
                agentSessionId: null,
                agentMessages: [],
                agentStatus: 'idle',
                setAgentStatus: (agentStatus) => set({ agentStatus }),
                addAgentMessage: (message) => set((state) => ({
                    agentMessages: [...state.agentMessages, message],
                })),
                clearAgentSession: () => set({
                    agentSessionId: null,
                    agentMessages: [],
                    agentStatus: 'idle'
                }),
            }),
            {
                name: 'misata-studio-store',
                partialize: (state) => ({
                    story: state.story,
                    tables: state.tables,
                    relationships: state.relationships,
                    outcomeConstraints: state.outcomeConstraints,
                }),
            }
        ),
        { name: 'MisataStudio' }
    )
);

export default useStudioStore;
