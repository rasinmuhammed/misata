"use client";

import { useState, useCallback } from 'react';
import { useSchemaStore } from '@/store/schemaStore';
import {
    Link2,
    X,
    Copy,
    Check,
    Download,
    Table2,
    Columns3,
    GitBranch,
    Loader2,
    Save,
    Bookmark
} from 'lucide-react';

interface ShareModalProps {
    isOpen: boolean;
    onClose: () => void;
}

export default function ShareModal({ isOpen, onClose }: ShareModalProps) {
    const { tables, relationships, getSchemaConfig } = useSchemaStore();
    const [shareUrl, setShareUrl] = useState<string | null>(null);
    const [isGenerating, setIsGenerating] = useState(false);
    const [copied, setCopied] = useState(false);
    const [templateName, setTemplateName] = useState('');
    const [savedTemplate, setSavedTemplate] = useState(false);

    const generateShareLink = useCallback(async () => {
        setIsGenerating(true);

        try {
            const schema = getSchemaConfig();
            const schemaStr = JSON.stringify(schema);
            const encoded = btoa(unescape(encodeURIComponent(schemaStr)));
            const baseUrl = typeof window !== 'undefined' ? window.location.origin : '';
            const url = `${baseUrl}/import?schema=${encoded}`;
            setShareUrl(url);
        } catch (error) {
            console.error('Failed to generate share link:', error);
        } finally {
            setIsGenerating(false);
        }
    }, [getSchemaConfig]);

    const copyToClipboard = useCallback(async () => {
        if (shareUrl) {
            await navigator.clipboard.writeText(shareUrl);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        }
    }, [shareUrl]);

    const downloadJson = useCallback(() => {
        const schema = getSchemaConfig();
        const blob = new Blob([JSON.stringify(schema, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `misata_schema_${Date.now()}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }, [getSchemaConfig]);

    const saveAsTemplate = useCallback(() => {
        if (!templateName.trim()) return;

        const schema = getSchemaConfig();
        const template = {
            id: `custom_${Date.now()}`,
            name: templateName,
            description: `Custom template with ${tables.length} tables`,
            category: 'custom',
            createdAt: new Date().toISOString(),
            schema,
        };

        // Get existing custom templates
        const existingTemplates = JSON.parse(localStorage.getItem('misata_custom_templates') || '[]');
        existingTemplates.push(template);
        localStorage.setItem('misata_custom_templates', JSON.stringify(existingTemplates));

        setSavedTemplate(true);
        setTimeout(() => {
            setSavedTemplate(false);
            setTemplateName('');
        }, 2000);
    }, [templateName, tables.length, getSchemaConfig]);

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 animate-fade-in">
            <div className="card card-elevated w-full max-w-lg p-6 m-4">
                {/* Header */}
                <div className="flex items-center justify-between mb-6">
                    <h2 className="text-title text-[var(--text-primary)] flex items-center gap-2">
                        <Link2 className="w-5 h-5 text-[var(--accent-aurora)]" />
                        Share & Export
                    </h2>
                    <button
                        onClick={onClose}
                        className="btn btn-ghost btn-sm"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </div>

                {/* Schema Stats */}
                <div className="grid grid-cols-3 gap-4 mb-6">
                    <div className="bg-[var(--bg-nebula)] rounded-lg p-4 text-center border border-[var(--border-glass)]">
                        <div className="flex items-center justify-center gap-2 mb-1">
                            <Table2 className="w-4 h-4 text-[var(--accent-aurora)]" />
                            <span className="text-xl font-semibold text-[var(--text-primary)]">{tables.length}</span>
                        </div>
                        <p className="text-xs text-[var(--text-muted)]">Tables</p>
                    </div>
                    <div className="bg-[var(--bg-nebula)] rounded-lg p-4 text-center border border-[var(--border-glass)]">
                        <div className="flex items-center justify-center gap-2 mb-1">
                            <Columns3 className="w-4 h-4 text-[var(--accent-nebula)]" />
                            <span className="text-xl font-semibold text-[var(--text-primary)]">
                                {tables.reduce((a, t) => a + t.columns.length, 0)}
                            </span>
                        </div>
                        <p className="text-xs text-[var(--text-muted)]">Columns</p>
                    </div>
                    <div className="bg-[var(--bg-nebula)] rounded-lg p-4 text-center border border-[var(--border-glass)]">
                        <div className="flex items-center justify-center gap-2 mb-1">
                            <GitBranch className="w-4 h-4 text-[var(--accent-cosmic)]" />
                            <span className="text-xl font-semibold text-[var(--text-primary)]">{relationships.length}</span>
                        </div>
                        <p className="text-xs text-[var(--text-muted)]">Relations</p>
                    </div>
                </div>

                {/* Share Options */}
                <div className="space-y-4">
                    {/* Save as Template */}
                    <div className="space-y-2">
                        <label className="text-sm text-[var(--text-secondary)] flex items-center gap-2">
                            <Bookmark className="w-4 h-4" />
                            Save as Template
                        </label>
                        <div className="flex gap-2">
                            <input
                                type="text"
                                value={templateName}
                                onChange={(e) => setTemplateName(e.target.value)}
                                placeholder="Template name..."
                                className="input flex-1"
                                disabled={tables.length === 0}
                            />
                            <button
                                onClick={saveAsTemplate}
                                disabled={!templateName.trim() || tables.length === 0}
                                className={`btn ${savedTemplate ? 'bg-[var(--success)] border-[var(--success)] text-white' : 'btn-secondary'}`}
                            >
                                {savedTemplate ? <Check className="w-4 h-4" /> : <Save className="w-4 h-4" />}
                            </button>
                        </div>
                        {savedTemplate && (
                            <p className="text-xs text-[var(--success)]">Template saved! Find it in Templates page.</p>
                        )}
                    </div>

                    <div className="flex items-center gap-4">
                        <div className="flex-1 h-px bg-[var(--border-glass)]" />
                        <span className="text-xs text-[var(--text-muted)]">or share</span>
                        <div className="flex-1 h-px bg-[var(--border-glass)]" />
                    </div>

                    {/* Generate Link */}
                    {!shareUrl ? (
                        <button
                            onClick={generateShareLink}
                            disabled={isGenerating || tables.length === 0}
                            className="btn btn-primary w-full"
                        >
                            {isGenerating ? (
                                <>
                                    <Loader2 className="w-4 h-4 animate-spin" />
                                    Generating...
                                </>
                            ) : (
                                <>
                                    <Link2 className="w-4 h-4" />
                                    Generate Shareable Link
                                </>
                            )}
                        </button>
                    ) : (
                        <div className="space-y-2">
                            <label className="text-sm text-[var(--text-secondary)]">Shareable Link</label>
                            <div className="flex gap-2">
                                <input
                                    type="text"
                                    value={shareUrl}
                                    readOnly
                                    className="input flex-1 text-xs font-mono"
                                />
                                <button
                                    onClick={copyToClipboard}
                                    className={`btn ${copied ? 'bg-[var(--success)] border-[var(--success)] text-white' : 'btn-secondary'}`}
                                >
                                    {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                                </button>
                            </div>
                            <p className="text-xs text-[var(--text-muted)]">
                                Anyone with this link can import your schema
                            </p>
                        </div>
                    )}

                    <div className="flex items-center gap-4">
                        <div className="flex-1 h-px bg-[var(--border-glass)]" />
                        <span className="text-xs text-[var(--text-muted)]">or</span>
                        <div className="flex-1 h-px bg-[var(--border-glass)]" />
                    </div>

                    {/* Download JSON */}
                    <button
                        onClick={downloadJson}
                        disabled={tables.length === 0}
                        className="btn btn-secondary w-full"
                    >
                        <Download className="w-4 h-4" />
                        Download Schema JSON
                    </button>
                </div>

                {tables.length === 0 && (
                    <p className="text-xs text-[var(--text-muted)] text-center mt-4">
                        Add tables to your schema before sharing
                    </p>
                )}
            </div>
        </div>
    );
}

