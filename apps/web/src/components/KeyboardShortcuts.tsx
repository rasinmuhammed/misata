"use client";

import { useState, useEffect } from 'react';
import { Keyboard, X } from 'lucide-react';

interface KeyboardShortcutsProps {
    onAddTable: () => void;
    onGenerate: () => void;
    onShare: () => void;
    onUndo?: () => void;
    onRedo?: () => void;
    onClear?: () => void;
}

const shortcuts = [
    { key: 'z', label: 'Undo', description: 'Undo last action', mod: true },
    { key: 'z', label: 'Redo', description: 'Redo action', mod: true, shift: true },
    { key: 'n', label: 'New Table', description: 'Add a new table', mod: true },
    { key: 'g', label: 'Generate', description: 'Generate data', mod: true },
    { key: 's', label: 'Share', description: 'Share schema', mod: true },
    { key: '?', label: 'Help', description: 'Show shortcuts' },
    { key: 'Esc', label: 'Close', description: 'Close modals' },
];

export function useKeyboardShortcuts({
    onAddTable,
    onGenerate,
    onShare,
    onUndo,
    onRedo,
    onClear
}: KeyboardShortcutsProps) {
    const [showHelp, setShowHelp] = useState(false);

    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            // Ignore if typing in an input
            if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
                return;
            }

            // Ctrl/Cmd + key combinations
            if (e.metaKey || e.ctrlKey) {
                switch (e.key.toLowerCase()) {
                    case 'z':
                        e.preventDefault();
                        if (e.shiftKey) {
                            onRedo?.();
                        } else {
                            onUndo?.();
                        }
                        break;
                    case 'n':
                        e.preventDefault();
                        onAddTable();
                        break;
                    case 'g':
                        e.preventDefault();
                        onGenerate();
                        break;
                    case 's':
                        e.preventDefault();
                        onShare();
                        break;
                    case 'backspace':
                        e.preventDefault();
                        if (confirm('Clear all tables?')) {
                            onClear?.();
                        }
                        break;
                }
            }

            // Single key shortcuts
            if (e.key === '?') {
                setShowHelp(prev => !prev);
            }
            if (e.key === 'Escape') {
                setShowHelp(false);
            }
        };

        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [onAddTable, onGenerate, onShare, onUndo, onRedo, onClear]);

    return { showHelp, setShowHelp };
}

export function KeyboardShortcutsHelp({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 animate-fade-in">
            <div className="card w-full max-w-md m-4 p-6">
                <div className="flex items-center justify-between mb-6">
                    <h2 className="text-lg font-semibold text-[var(--text-primary)] flex items-center gap-2">
                        <Keyboard className="w-5 h-5 text-[var(--accent-aurora)]" />
                        Keyboard Shortcuts
                    </h2>
                    <button
                        onClick={onClose}
                        className="text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </div>

                <div className="space-y-3">
                    {shortcuts.map((shortcut, i) => (
                        <div key={i} className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                <kbd className="px-2 py-1 bg-[var(--bg-nebula)] border border-[var(--border-glass)] rounded text-xs text-[var(--text-secondary)] font-mono min-w-[70px] text-center">
                                    {shortcut.key === 'Esc'
                                        ? 'Esc'
                                        : shortcut.key === '?'
                                            ? '?'
                                            : shortcut.shift
                                                ? `⌘⇧${shortcut.key.toUpperCase()}`
                                                : `⌘${shortcut.key.toUpperCase()}`}
                                </kbd>
                                <span className="text-[var(--text-primary)] text-sm">{shortcut.label}</span>
                            </div>
                            <span className="text-[var(--text-muted)] text-xs">{shortcut.description}</span>
                        </div>
                    ))}
                </div>

                <div className="mt-6 pt-4 border-t border-[var(--border-glass)]">
                    <p className="text-xs text-[var(--text-muted)] text-center">
                        Press <kbd className="px-1.5 py-0.5 bg-[var(--bg-nebula)] border border-[var(--border-glass)] rounded text-[var(--text-secondary)]">?</kbd> to toggle this menu
                    </p>
                </div>
            </div>
        </div>
    );
}

