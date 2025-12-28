"use client";

import { useState, useEffect } from 'react';
import { checkApiHealth } from '@/lib/api';
import {
    Settings as SettingsIcon,
    Server,
    CheckCircle,
    XCircle,
    Loader2,
    Cpu,
    Zap,
    Cloud,
    Home,
    Keyboard,
    AlertTriangle,
    Trash2,
    Save
} from 'lucide-react';

const llmProviders = [
    { id: 'groq', name: 'Groq', description: 'Ultra-fast inference', icon: Zap },
    { id: 'openai', name: 'OpenAI', description: 'GPT-4 quality', icon: Cloud },
    { id: 'ollama', name: 'Ollama', description: 'Local models', icon: Home },
];

const shortcuts = [
    { keys: ['Cmd', 'N'], action: 'New table' },
    { keys: ['Cmd', 'G'], action: 'Generate' },
    { keys: ['Cmd', 'S'], action: 'Share' },
    { keys: ['?'], action: 'Help' },
];

export default function SettingsPage() {
    const [apiUrl, setApiUrl] = useState('http://localhost:8000');
    const [llmProvider, setLlmProvider] = useState('groq');
    const [defaultRows, setDefaultRows] = useState('1000');
    const [saved, setSaved] = useState(false);
    const [apiStatus, setApiStatus] = useState<'checking' | 'online' | 'offline'>('checking');

    useEffect(() => {
        checkApiHealth().then(isHealthy => {
            setApiStatus(isHealthy ? 'online' : 'offline');
        });
    }, []);

    const handleSave = () => {
        localStorage.setItem('misata_settings', JSON.stringify({
            apiUrl,
            llmProvider,
            defaultRows: parseInt(defaultRows),
        }));
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
    };

    const handleClearData = () => {
        if (confirm('This will clear all local data including job history. Continue?')) {
            localStorage.removeItem('misata_jobs');
            localStorage.removeItem('misata_settings');
            window.location.reload();
        }
    };

    return (
        <div className="p-8 max-w-3xl mx-auto animate-fade-in">
            {/* Header */}
            <div className="mb-8">
                <div className="flex items-center gap-3 mb-2">
                    <div className="w-10 h-10 rounded-lg bg-[var(--accent-muted)] flex items-center justify-center">
                        <SettingsIcon className="w-5 h-5 text-[var(--brand-primary-light)]" />
                    </div>
                    <h1 className="text-heading text-[var(--text-primary)]">
                        Settings
                    </h1>
                </div>
                <p className="text-body">
                    Configure your Misata instance.
                </p>
            </div>

            {/* System Status */}
            <section className="card p-6 mb-6">
                <h2 className="text-title text-[var(--text-primary)] mb-4 flex items-center gap-2">
                    <Server className="w-4 h-4 text-[var(--text-muted)]" />
                    System Status
                </h2>
                <div className="grid grid-cols-2 gap-4">
                    <div className="bg-[var(--bg-secondary)] rounded-lg p-4">
                        <p className="text-xs text-[var(--text-muted)] mb-2">API Server</p>
                        <div className="flex items-center gap-2">
                            {apiStatus === 'checking' ? (
                                <Loader2 className="w-4 h-4 text-[var(--text-muted)] animate-spin" />
                            ) : apiStatus === 'online' ? (
                                <CheckCircle className="w-4 h-4 text-[var(--success)]" />
                            ) : (
                                <XCircle className="w-4 h-4 text-[var(--error)]" />
                            )}
                            <span className={`text-sm font-medium ${apiStatus === 'online' ? 'text-[var(--success)]' :
                                    apiStatus === 'offline' ? 'text-[var(--error)]' :
                                        'text-[var(--text-muted)]'
                                }`}>
                                {apiStatus === 'checking' ? 'Checking...' :
                                    apiStatus === 'online' ? 'Connected' : 'Disconnected'}
                            </span>
                        </div>
                    </div>
                    <div className="bg-[var(--bg-secondary)] rounded-lg p-4">
                        <p className="text-xs text-[var(--text-muted)] mb-2">Version</p>
                        <p className="text-sm font-medium text-[var(--text-primary)]">v0.1.0-beta</p>
                    </div>
                </div>
            </section>

            {/* API Configuration */}
            <section className="card p-6 mb-6">
                <h2 className="text-title text-[var(--text-primary)] mb-4 flex items-center gap-2">
                    <Server className="w-4 h-4 text-[var(--text-muted)]" />
                    API Configuration
                </h2>
                <div>
                    <label className="block text-sm font-medium text-[var(--text-secondary)] mb-2">
                        Backend URL
                    </label>
                    <input
                        type="url"
                        value={apiUrl}
                        onChange={(e) => setApiUrl(e.target.value)}
                        className="input"
                        placeholder="http://localhost:8000"
                    />
                    <p className="text-xs text-[var(--text-muted)] mt-2">
                        The URL where the Misata API server is running.
                    </p>
                </div>
            </section>

            {/* AI Provider */}
            <section className="card p-6 mb-6">
                <h2 className="text-title text-[var(--text-primary)] mb-4 flex items-center gap-2">
                    <Cpu className="w-4 h-4 text-[var(--text-muted)]" />
                    AI Provider
                </h2>
                <p className="text-sm text-[var(--text-secondary)] mb-4">
                    Select the LLM provider for Story Mode schema generation.
                </p>
                <div className="grid grid-cols-3 gap-3">
                    {llmProviders.map((provider) => {
                        const Icon = provider.icon;
                        return (
                            <button
                                key={provider.id}
                                onClick={() => setLlmProvider(provider.id)}
                                className={`card p-4 text-left transition-all ${llmProvider === provider.id
                                        ? 'border-[var(--brand-primary)] bg-[var(--accent-muted)]'
                                        : 'hover:border-[var(--border-default)]'
                                    }`}
                            >
                                <Icon className={`w-5 h-5 mb-2 ${llmProvider === provider.id
                                        ? 'text-[var(--brand-primary-light)]'
                                        : 'text-[var(--text-muted)]'
                                    }`} />
                                <p className="font-medium text-[var(--text-primary)] text-sm">{provider.name}</p>
                                <p className="text-xs text-[var(--text-muted)]">{provider.description}</p>
                            </button>
                        );
                    })}
                </div>
            </section>

            {/* Generation Defaults */}
            <section className="card p-6 mb-6">
                <h2 className="text-title text-[var(--text-primary)] mb-4 flex items-center gap-2">
                    <SettingsIcon className="w-4 h-4 text-[var(--text-muted)]" />
                    Generation Defaults
                </h2>
                <div>
                    <label className="block text-sm font-medium text-[var(--text-secondary)] mb-2">
                        Default row count per table
                    </label>
                    <input
                        type="number"
                        value={defaultRows}
                        onChange={(e) => setDefaultRows(e.target.value)}
                        className="input w-48"
                        min="10"
                        max="1000000"
                    />
                    <p className="text-xs text-[var(--text-muted)] mt-2">
                        Applied when creating new tables. Can be changed per table.
                    </p>
                </div>
            </section>

            {/* Keyboard Shortcuts */}
            <section className="card p-6 mb-6">
                <h2 className="text-title text-[var(--text-primary)] mb-4 flex items-center gap-2">
                    <Keyboard className="w-4 h-4 text-[var(--text-muted)]" />
                    Keyboard Shortcuts
                </h2>
                <div className="grid grid-cols-2 gap-3">
                    {shortcuts.map((shortcut) => (
                        <div key={shortcut.action} className="flex items-center gap-3 p-3 bg-[var(--bg-secondary)] rounded-lg">
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
            </section>

            {/* Danger Zone */}
            <section className="card p-6 border-[var(--error)]/30">
                <h2 className="text-title text-[var(--error)] mb-4 flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4" />
                    Danger Zone
                </h2>
                <div className="flex items-center justify-between">
                    <div>
                        <p className="text-sm text-[var(--text-primary)]">Clear all local data</p>
                        <p className="text-xs text-[var(--text-muted)]">Removes all saved settings and job history</p>
                    </div>
                    <button
                        onClick={handleClearData}
                        className="btn btn-danger btn-sm"
                    >
                        <Trash2 className="w-3.5 h-3.5" />
                        Clear Data
                    </button>
                </div>
            </section>

            {/* Save Button */}
            <div className="flex justify-end mt-6">
                <button
                    onClick={handleSave}
                    className={`btn ${saved ? 'bg-[var(--success)] border-[var(--success)] text-white' : 'btn-primary'}`}
                >
                    {saved ? (
                        <>
                            <CheckCircle className="w-4 h-4" />
                            Saved
                        </>
                    ) : (
                        <>
                            <Save className="w-4 h-4" />
                            Save Settings
                        </>
                    )}
                </button>
            </div>
        </div>
    );
}
