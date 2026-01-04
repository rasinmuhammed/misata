"use client";

import Link from 'next/link';
import {
    Book,
    Rocket,
    Table2,
    Columns3,
    GitBranch,
    Code2,
    Keyboard,
    ExternalLink,
    Hash,
    Type,
    Calendar,
    ToggleLeft,
    List,
    Link2,
    Activity
} from 'lucide-react';

const columnTypes = [
    { type: 'int', icon: Hash, description: 'Integer numbers (IDs, counts, quantities)' },
    { type: 'float', icon: Hash, description: 'Decimal numbers (prices, scores, percentages)' },
    { type: 'text', icon: Type, description: 'Text strings (names, emails, addresses)' },
    { type: 'date', icon: Calendar, description: 'Dates (2024-01-15)' },
    { type: 'time', icon: Calendar, description: 'Time of day (14:30:00)' },
    { type: 'datetime', icon: Calendar, description: 'Full timestamp (2024-01-15 14:30:00)' },
    { type: 'categorical', icon: List, description: 'Fixed set of options (status, type)' },
    { type: 'boolean', icon: ToggleLeft, description: 'True/false values (is_active, has_permission)' },
    { type: 'foreign_key', icon: Link2, description: 'Reference to another table (user_id, order_id)' },
];

const endpoints = [
    { method: 'GET', path: '/', description: 'Health check' },
    { method: 'POST', path: '/jobs', description: 'Submit data generation job' },
    { method: 'GET', path: '/jobs/{id}', description: 'Get job status and progress' },
    { method: 'GET', path: '/jobs/{id}/download', description: 'Download generated files (CSV/ZIP)' },
    { method: 'GET', path: '/jobs/{id}/quality-report', description: 'Get statistical quality scores' },
    { method: 'GET', path: '/jobs/{id}/export/json', description: 'Export full job data as JSON' },
    { method: 'GET', path: '/jobs/{id}/export/sql', description: 'Export SQL CREATE/INSERT statements' },
    { method: 'POST', path: '/schema/generate', description: 'Generate schema from natural language' },
    { method: 'GET', path: '/templates', description: 'List available schema templates' },
    { method: 'GET', path: '/config/llm', description: 'Get current LLM configuration' },
    { method: 'POST', path: '/config/llm', description: 'Update LLM provider/key' },
];

const shortcuts = [
    { keys: ['Cmd', 'N'], action: 'Add new table' },
    { keys: ['Cmd', 'G'], action: 'Generate data' },
    { keys: ['Cmd', 'S'], action: 'Share schema' },
    { keys: ['?'], action: 'Show keyboard shortcuts' },
    { keys: ['Esc'], action: 'Close modal' },
];

export default function DocsPage() {
    return (
        <div className="flex animate-fade-in">
            {/* Sidebar Navigation */}
            <aside className="w-56 flex-shrink-0 border-r border-[var(--border-subtle)] h-[calc(100vh-64px)] sticky top-0 overflow-y-auto p-4">
                <nav className="space-y-6">
                    <div>
                        <h4 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-2 px-2">
                            Getting Started
                        </h4>
                        <ul className="space-y-1">
                            <li>
                                <a href="#quick-start" className="flex items-center gap-2 px-2 py-1.5 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] rounded transition-colors">
                                    <Rocket className="w-3.5 h-3.5" />
                                    Quick Start
                                </a>
                            </li>
                            <li>
                                <a href="#creating-tables" className="flex items-center gap-2 px-2 py-1.5 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] rounded transition-colors">
                                    <Table2 className="w-3.5 h-3.5" />
                                    Creating Tables
                                </a>
                            </li>
                        </ul>
                    </div>
                    <div>
                        <h4 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-2 px-2">
                            Reference
                        </h4>
                        <ul className="space-y-1">
                            <li>
                                <a href="#column-types" className="flex items-center gap-2 px-2 py-1.5 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] rounded transition-colors">
                                    <Columns3 className="w-3.5 h-3.5" />
                                    Column Types
                                </a>
                            </li>
                            <li>
                                <a href="#api-reference" className="flex items-center gap-2 px-2 py-1.5 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] rounded transition-colors">
                                    <Code2 className="w-3.5 h-3.5" />
                                    API Reference
                                </a>
                            </li>
                            <li>
                                <a href="#shortcuts" className="flex items-center gap-2 px-2 py-1.5 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] rounded transition-colors">
                                    <Keyboard className="w-3.5 h-3.5" />
                                    Shortcuts
                                </a>
                            </li>
                        </ul>
                    </div>
                    <div>
                        <h4 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-2 px-2">
                            Advanced
                        </h4>
                        <ul className="space-y-1">
                            <li>
                                <a href="#quality-reports" className="flex items-center gap-2 px-2 py-1.5 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] rounded transition-colors">
                                    <Activity className="w-3.5 h-3.5" />
                                    Quality Reports
                                </a>
                            </li>
                            <li>
                                <a href="#exports" className="flex items-center gap-2 px-2 py-1.5 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] rounded transition-colors">
                                    <ExternalLink className="w-3.5 h-3.5" />
                                    Exports
                                </a>
                            </li>
                        </ul>
                    </div>
                </nav>
            </aside>

            {/* Main Content */}
            <main className="flex-1 p-8 max-w-3xl">
                {/* Header */}
                <div className="mb-12">
                    <div className="flex items-center gap-3 mb-3">
                        <div className="w-10 h-10 rounded-lg bg-[var(--accent-muted)] flex items-center justify-center">
                            <Book className="w-5 h-5 text-[var(--brand-primary-light)]" />
                        </div>
                        <h1 className="text-heading text-[var(--text-primary)]">
                            Documentation
                        </h1>
                    </div>
                    <p className="text-body">
                        Everything you need to generate production-ready synthetic data.
                    </p>
                </div>

                {/* Quick Start */}
                <section id="quick-start" className="mb-12 scroll-mt-8">
                    <h2 className="text-title text-[var(--text-primary)] mb-4 flex items-center gap-2">
                        <Rocket className="w-5 h-5 text-[var(--brand-primary-light)]" />
                        Quick Start
                    </h2>
                    <div className="card p-6">
                        <p className="text-sm text-[var(--text-secondary)] mb-4">
                            Misata provides three ways to generate synthetic data:
                        </p>
                        <ol className="list-decimal list-outside ml-5 space-y-3 text-sm text-[var(--text-secondary)]">
                            <li>
                                <strong className="text-[var(--text-primary)]">Visual Builder</strong> — Design tables and relationships with drag-and-drop
                            </li>
                            <li>
                                <strong className="text-[var(--text-primary)]">Story Mode</strong> — Describe your data in plain English and let AI generate the schema
                            </li>
                            <li>
                                <strong className="text-[var(--text-primary)]">Templates</strong> — Start with pre-built schemas for common use cases
                            </li>
                        </ol>
                        <div className="flex gap-3 mt-6">
                            <Link href="/" className="btn btn-primary btn-sm">
                                Open Builder
                            </Link>
                            <Link href="/story" className="btn btn-secondary btn-sm">
                                Try Story Mode
                            </Link>
                        </div>
                    </div>
                </section>

                {/* Creating Tables */}
                <section id="creating-tables" className="mb-12 scroll-mt-8">
                    <h2 className="text-title text-[var(--text-primary)] mb-4 flex items-center gap-2">
                        <Table2 className="w-5 h-5 text-[var(--brand-primary-light)]" />
                        Creating Tables
                    </h2>
                    <div className="card p-6">
                        <ol className="list-decimal list-outside ml-5 space-y-3 text-sm text-[var(--text-secondary)]">
                            <li>Click <strong className="text-[var(--brand-primary-light)]">Add Table</strong> in the toolbar</li>
                            <li>Double-click the table header to rename and set row count</li>
                            <li>Click <strong className="text-[var(--brand-primary-light)]">Add Column</strong> to add fields</li>
                            <li>Click any column to configure type, distribution, and parameters</li>
                            <li>Drag from a column handle to another table to create a relationship</li>
                        </ol>
                    </div>
                </section>

                {/* Column Types */}
                <section id="column-types" className="mb-12 scroll-mt-8">
                    <h2 className="text-title text-[var(--text-primary)] mb-4 flex items-center gap-2">
                        <Columns3 className="w-5 h-5 text-[var(--brand-primary-light)]" />
                        Column Types
                    </h2>
                    <div className="card divide-y divide-[var(--border-subtle)]">
                        {columnTypes.map((col) => {
                            const Icon = col.icon;
                            return (
                                <div key={col.type} className="flex items-center gap-4 p-4">
                                    <div className="w-8 h-8 rounded bg-[var(--bg-secondary)] flex items-center justify-center">
                                        <Icon className="w-4 h-4 text-[var(--text-muted)]" />
                                    </div>
                                    <div>
                                        <code className="text-sm font-medium text-[var(--brand-primary-light)]">{col.type}</code>
                                        <p className="text-xs text-[var(--text-tertiary)]">{col.description}</p>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </section>

                {/* Quality Reports */}
                <section id="quality-reports" className="mb-12 scroll-mt-8">
                    <h2 className="text-title text-[var(--text-primary)] mb-4 flex items-center gap-2">
                        <Activity className="w-5 h-5 text-[var(--brand-primary-light)]" />
                        Quality Reports
                    </h2>
                    <div className="card p-6">
                        <p className="text-sm text-[var(--text-secondary)] mb-4">
                            Misata generates statistical quality scores for every job to ensure data reliability:
                        </p>
                        <ul className="list-disc list-outside ml-5 space-y-2 text-sm text-[var(--text-secondary)]">
                            <li><strong className="text-[var(--text-primary)]">Completeness</strong>: Percentage of non-null values</li>
                            <li><strong className="text-[var(--text-primary)]">Integrity</strong>: Referential integrity checks for foreign keys</li>
                            <li><strong className="text-[var(--text-primary)]">Coverage</strong>: Statistical distribution overlap with expected parameters</li>
                        </ul>
                        <p className="mt-4 text-sm text-[var(--text-secondary)]">
                            Access via: <code className="bg-[var(--bg-secondary)] px-1.5 py-0.5 rounded text-[var(--brand-primary-light)]">GET /jobs/:id/quality-report</code>
                        </p>
                    </div>
                </section>

                {/* Exports */}
                <section id="exports" className="mb-12 scroll-mt-8">
                    <h2 className="text-title text-[var(--text-primary)] mb-4 flex items-center gap-2">
                        <ExternalLink className="w-5 h-5 text-[var(--brand-primary-light)]" />
                        Exports & Integrations
                    </h2>
                    <div className="card p-6">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div className="p-4 bg-[var(--bg-secondary)] rounded-lg">
                                <h3 className="font-medium text-[var(--text-primary)] mb-2">JSON Format</h3>
                                <p className="text-xs text-[var(--text-secondary)] mb-2">Full hierarchical structure including metadata.</p>
                                <code className="text-xs text-[var(--brand-primary-light)]">/jobs/:id/export/json</code>
                            </div>
                            <div className="p-4 bg-[var(--bg-secondary)] rounded-lg">
                                <h3 className="font-medium text-[var(--text-primary)] mb-2">SQL Dump</h3>
                                <p className="text-xs text-[var(--text-secondary)] mb-2">CREATE TABLE and INSERT statements.</p>
                                <code className="text-xs text-[var(--brand-primary-light)]">/jobs/:id/export/sql</code>
                            </div>
                        </div>
                    </div>
                </section>

                {/* API Reference */}
                <section id="api-reference" className="mb-12 scroll-mt-8">
                    <h2 className="text-title text-[var(--text-primary)] mb-4 flex items-center gap-2">
                        <Code2 className="w-5 h-5 text-[var(--brand-primary-light)]" />
                        API Reference
                    </h2>
                    <div className="card overflow-hidden">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
                                    <th className="text-left py-3 px-4 font-medium text-[var(--text-tertiary)]">Method</th>
                                    <th className="text-left py-3 px-4 font-medium text-[var(--text-tertiary)]">Endpoint</th>
                                    <th className="text-left py-3 px-4 font-medium text-[var(--text-tertiary)]">Description</th>
                                </tr>
                            </thead>
                            <tbody>
                                {endpoints.map((ep) => (
                                    <tr key={`${ep.method}-${ep.path}`} className="border-b border-[var(--border-subtle)] last:border-0">
                                        <td className="py-3 px-4">
                                            <span className={`text-xs font-mono px-1.5 py-0.5 rounded ${ep.method === 'GET'
                                                ? 'bg-[var(--success-muted)] text-[var(--success)]'
                                                : 'bg-[var(--info-muted)] text-[var(--info)]'
                                                }`}>
                                                {ep.method}
                                            </span>
                                        </td>
                                        <td className="py-3 px-4 font-mono text-[var(--text-secondary)]">{ep.path}</td>
                                        <td className="py-3 px-4 text-[var(--text-tertiary)]">{ep.description}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                    <p className="mt-4 text-xs text-[var(--text-muted)]">
                        Full API documentation available at{' '}
                        <a href="http://localhost:8000/docs" target="_blank" rel="noopener noreferrer" className="text-[var(--brand-primary-light)] hover:underline inline-flex items-center gap-1">
                            localhost:8000/docs
                            <ExternalLink className="w-3 h-3" />
                        </a>
                    </p>
                </section>

                {/* Keyboard Shortcuts */}
                <section id="shortcuts" className="mb-12 scroll-mt-8">
                    <h2 className="text-title text-[var(--text-primary)] mb-4 flex items-center gap-2">
                        <Keyboard className="w-5 h-5 text-[var(--brand-primary-light)]" />
                        Keyboard Shortcuts
                    </h2>
                    <div className="card p-4">
                        <div className="grid grid-cols-2 gap-3">
                            {shortcuts.map((shortcut) => (
                                <div key={shortcut.action} className="flex items-center gap-3 p-2 bg-[var(--bg-secondary)] rounded-lg">
                                    <div className="flex gap-1">
                                        {shortcut.keys.map((key) => (
                                            <kbd key={key} className="px-2 py-1 bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded text-xs font-mono text-[var(--text-secondary)]">
                                                {key}
                                            </kbd>
                                        ))}
                                    </div>
                                    <span className="text-sm text-[var(--text-tertiary)]">{shortcut.action}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                </section>
            </main>
        </div>
    );
}
