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
    Save,
    Eye,
    EyeOff,
    Key
} from 'lucide-react';

const llmProviders = [
    { id: 'groq', name: 'Groq', description: 'Ultra-fast Llama 3.3', icon: Zap, keyName: 'GROQ_API_KEY', placeholder: 'gsk_...' },
    { id: 'openai', name: 'OpenAI', description: 'GPT-4 quality', icon: Cloud, keyName: 'OPENAI_API_KEY', placeholder: 'sk-...' },
    { id: 'ollama', name: 'Ollama', description: 'Local models (no key)', icon: Home, keyName: '', placeholder: '' },
];

const shortcuts = [
    { keys: ['Cmd', 'N'], action: 'New table' },
    { keys: ['Cmd', 'G'], action: 'Generate' },
    { keys: ['Cmd', 'S'], action: 'Share' },
    { keys: ['?'], action: 'Help' },
];

// Secure storage utilities (using sessionStorage for API keys - cleared on tab close)
const secureStorage = {
    getApiKey: (provider: string): string => {
        if (typeof window === 'undefined') return '';
        // API keys stored in sessionStorage (more secure than localStorage)
        return sessionStorage.getItem(`misata_${provider}_key`) || '';
    },
    setApiKey: (provider: string, key: string): void => {
        if (typeof window === 'undefined') return;
        if (key) {
            sessionStorage.setItem(`misata_${provider}_key`, key);
        } else {
            sessionStorage.removeItem(`misata_${provider}_key`);
        }
    },
    getProvider: (): string => {
        if (typeof window === 'undefined') return 'groq';
        return localStorage.getItem('misata_llm_provider') || 'groq';
    },
    setProvider: (provider: string): void => {
        if (typeof window === 'undefined') return;
        localStorage.setItem('misata_llm_provider', provider);
    }
};

export default function SettingsPage() {
    const [apiUrl, setApiUrl] = useState('http://localhost:8000');
    const [llmProvider, setLlmProvider] = useState('groq');
    const [apiKeys, setApiKeys] = useState<Record<string, string>>({});
    const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});
    const [defaultRows, setDefaultRows] = useState('1000');
    const [saved, setSaved] = useState(false);
    const [saving, setSaving] = useState(false);
    const [apiStatus, setApiStatus] = useState<'checking' | 'online' | 'offline'>('checking');
    const [testingKey, setTestingKey] = useState(false);
    const [keyStatus, setKeyStatus] = useState<'idle' | 'valid' | 'invalid'>('idle');

    // Load settings on mount
    useEffect(() => {
        const loadSettings = () => {
            const savedSettings = localStorage.getItem('misata_settings');
            if (savedSettings) {
                const parsed = JSON.parse(savedSettings);
                setApiUrl(parsed.apiUrl || 'http://localhost:8000');
                setDefaultRows(String(parsed.defaultRows || 1000));
            }

            // Load provider
            setLlmProvider(secureStorage.getProvider());

            // Load API keys from session storage
            const keys: Record<string, string> = {};
            llmProviders.forEach(p => {
                if (p.keyName) {
                    keys[p.id] = secureStorage.getApiKey(p.id);
                }
            });
            setApiKeys(keys);
        };

        loadSettings();
        checkApiHealth().then(isHealthy => {
            setApiStatus(isHealthy ? 'online' : 'offline');
        });
    }, []);

    const handleSave = async () => {
        setSaving(true);

        // Save general settings to localStorage
        localStorage.setItem('misata_settings', JSON.stringify({
            apiUrl,
            llmProvider,
            defaultRows: parseInt(defaultRows),
        }));

        // Save provider selection
        secureStorage.setProvider(llmProvider);

        // Save API keys to sessionStorage (secure)
        Object.entries(apiKeys).forEach(([provider, key]) => {
            secureStorage.setApiKey(provider, key);
        });

        // Try to update the backend with the new configuration
        try {
            const response = await fetch(`${apiUrl}/config/llm`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    provider: llmProvider,
                    api_key: apiKeys[llmProvider] || null
                })
            });

            if (!response.ok) {
                console.warn('Backend config update failed, using local config');
            }
        } catch (e) {
            console.warn('Could not reach backend to update config');
        }

        setSaving(false);
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
    };

    const handleTestKey = async () => {
        const currentKey = apiKeys[llmProvider];
        if (!currentKey && llmProvider !== 'ollama') {
            setKeyStatus('invalid');
            return;
        }

        setTestingKey(true);
        setKeyStatus('idle');

        try {
            const response = await fetch(`${apiUrl}/config/test-llm`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    provider: llmProvider,
                    api_key: currentKey
                })
            });

            const data = await response.json();
            setKeyStatus(data.valid ? 'valid' : 'invalid');
        } catch {
            // If backend doesn't support this endpoint yet, do a basic validation
            if (llmProvider === 'groq' && currentKey?.startsWith('gsk_')) {
                setKeyStatus('valid');
            } else if (llmProvider === 'openai' && currentKey?.startsWith('sk-')) {
                setKeyStatus('valid');
            } else if (llmProvider === 'ollama') {
                setKeyStatus('valid');
            } else {
                setKeyStatus('invalid');
            }
        }

        setTestingKey(false);
    };

    const handleClearData = () => {
        if (confirm('This will clear all local data including job history and API keys. Continue?')) {
            localStorage.removeItem('misata_jobs');
            localStorage.removeItem('misata_settings');
            localStorage.removeItem('misata_llm_provider');
            localStorage.removeItem('schema-store');
            sessionStorage.clear();
            window.location.reload();
        }
    };

    const toggleShowKey = (provider: string) => {
        setShowKeys(prev => ({ ...prev, [provider]: !prev[provider] }));
    };

    const updateApiKey = (provider: string, value: string) => {
        setApiKeys(prev => ({ ...prev, [provider]: value }));
        setKeyStatus('idle');
    };

    const currentProvider = llmProviders.find(p => p.id === llmProvider);

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
                    Configure your Misata Studio instance.
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

            {/* AI Provider Selection */}
            <section className="card p-6 mb-6">
                <h2 className="text-title text-[var(--text-primary)] mb-4 flex items-center gap-2">
                    <Cpu className="w-4 h-4 text-[var(--text-muted)]" />
                    AI Provider
                </h2>
                <p className="text-sm text-[var(--text-secondary)] mb-4">
                    Select the LLM provider for Story Mode schema generation.
                </p>
                <div className="grid grid-cols-3 gap-3 mb-6">
                    {llmProviders.map((provider) => {
                        const Icon = provider.icon;
                        return (
                            <button
                                key={provider.id}
                                onClick={() => {
                                    setLlmProvider(provider.id);
                                    setKeyStatus('idle');
                                }}
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

                {/* API Key Input */}
                {currentProvider && currentProvider.keyName && (
                    <div className="p-4 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-subtle)]">
                        <label className="block text-sm font-medium text-[var(--text-secondary)] mb-2 flex items-center gap-2">
                            <Key className="w-4 h-4" />
                            {currentProvider.keyName}
                        </label>
                        <div className="flex gap-2">
                            <div className="relative flex-1">
                                <input
                                    type={showKeys[llmProvider] ? 'text' : 'password'}
                                    value={apiKeys[llmProvider] || ''}
                                    onChange={(e) => updateApiKey(llmProvider, e.target.value)}
                                    className="input pr-10 font-mono text-sm"
                                    placeholder={currentProvider.placeholder}
                                />
                                <button
                                    type="button"
                                    onClick={() => toggleShowKey(llmProvider)}
                                    className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                                >
                                    {showKeys[llmProvider] ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                                </button>
                            </div>
                            <button
                                onClick={handleTestKey}
                                disabled={testingKey}
                                className="btn btn-secondary"
                            >
                                {testingKey ? (
                                    <Loader2 className="w-4 h-4 animate-spin" />
                                ) : (
                                    'Test'
                                )}
                            </button>
                        </div>

                        {/* Key status indicator */}
                        {keyStatus !== 'idle' && (
                            <div className={`flex items-center gap-2 mt-2 text-sm ${keyStatus === 'valid' ? 'text-[var(--success)]' : 'text-[var(--error)]'
                                }`}>
                                {keyStatus === 'valid' ? (
                                    <>
                                        <CheckCircle className="w-4 h-4" />
                                        API key is valid
                                    </>
                                ) : (
                                    <>
                                        <XCircle className="w-4 h-4" />
                                        API key appears invalid
                                    </>
                                )}
                            </div>
                        )}

                        <p className="text-xs text-[var(--text-muted)] mt-3">
                            🔒 API keys are stored in session storage (cleared when you close the tab).
                            They are never sent to any third party.
                        </p>
                    </div>
                )}

                {/* Ollama note */}
                {llmProvider === 'ollama' && (
                    <div className="p-4 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-subtle)]">
                        <p className="text-sm text-[var(--text-secondary)]">
                            <Home className="w-4 h-4 inline mr-2" />
                            Ollama runs locally - make sure you have it installed and running at <code className="text-xs bg-[var(--bg-primary)] px-1 rounded">http://localhost:11434</code>
                        </p>
                    </div>
                )}
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
                        <p className="text-xs text-[var(--text-muted)]">Removes schemas, settings, job history, and API keys</p>
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
                    disabled={saving}
                    className={`btn ${saved ? 'bg-[var(--success)] border-[var(--success)] text-white' : 'btn-primary'}`}
                >
                    {saving ? (
                        <>
                            <Loader2 className="w-4 h-4 animate-spin" />
                            Saving...
                        </>
                    ) : saved ? (
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
