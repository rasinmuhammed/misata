"use client";

import { useState, useEffect, useMemo } from 'react';
import { Column, useSchemaStore } from '@/store/schemaStore';
import { validateColumnName, validateDistributionParams, ValidationResult } from '@/lib/validation';
import { Sparkles, Brain, AlertCircle, AlertTriangle } from 'lucide-react';

interface ColumnEditorProps {
    tableId: string;
    column: Column;
    onClose: () => void;
}

const columnTypes = [
    { value: 'int', label: 'Integer', icon: '🔢' },
    { value: 'float', label: 'Float', icon: '📊' },
    { value: 'text', label: 'Text', icon: '📝' },
    { value: 'date', label: 'Date', icon: '📅' },
    { value: 'categorical', label: 'Categorical', icon: '🏷️' },
    { value: 'boolean', label: 'Boolean', icon: '✓' },
    { value: 'foreign_key', label: 'Foreign Key', icon: '🔗' },
];

const distributions: Record<string, string[]> = {
    int: ['sequence', 'uniform', 'normal', 'poisson'],
    float: ['uniform', 'normal', 'exponential'],
    text: ['fake.name', 'fake.email', 'fake.address', 'fake.company', 'fake.text', 'uuid'],
    date: ['uniform', 'recent', 'past', 'future'],
    time: ['uniform'],
    datetime: ['uniform', 'recent', 'past', 'future'],
    categorical: ['choices'],
    boolean: ['bernoulli'],
    foreign_key: ['reference'],
};

const smartDomains = [
    { value: '', label: 'Auto-detect from column name' },
    { value: 'disease', label: 'Medical - Diseases/Conditions' },
    { value: 'prescription', label: 'Medical - Prescriptions' },
    { value: 'procedure', label: 'Medical - Procedures' },
    { value: 'symptom', label: 'Medical - Symptoms' },
    { value: 'job_title', label: 'HR - Job Titles' },
    { value: 'department', label: 'HR - Departments' },
    { value: 'product', label: 'Retail - Products' },
    { value: 'category', label: 'Retail - Categories' },
    { value: 'custom', label: 'Custom (specify context)' },
];

export default function ColumnEditor({ tableId, column, onClose }: ColumnEditorProps) {
    const { updateColumn, removeColumn, tables } = useSchemaStore();

    const [name, setName] = useState(column.name);
    const [type, setType] = useState<Column['type']>(column.type);
    const [distribution, setDistribution] = useState(
        column.distributionParams?.distribution as string || 'sequence'
    );
    const [choices, setChoices] = useState(
        (column.distributionParams?.choices as string[])?.join(', ') || ''
    );
    const [min, setMin] = useState(column.distributionParams?.min as number || 0);
    const [max, setMax] = useState(column.distributionParams?.max as number || 100);
    const [refTable, setRefTable] = useState(column.distributionParams?.reference_table as string || '');

    // Smart generation state
    const [smartGenerate, setSmartGenerate] = useState(
        column.distributionParams?.smart_generate as boolean || false
    );
    const [domainHint, setDomainHint] = useState(
        column.distributionParams?.domain_hint as string || ''
    );
    const [context, setContext] = useState(
        column.distributionParams?.context as string || ''
    );

    // Get current table for validation
    const currentTable = tables.find(t => t.id === tableId);
    const tableName = currentTable?.name || '';
    const existingColumnNames = (currentTable?.columns || [])
        .filter(c => c.id !== column.id)
        .map(c => c.name);

    // Inline validation for column name
    const nameValidation = useMemo((): ValidationResult => {
        return validateColumnName(name, existingColumnNames, tableName);
    }, [name, existingColumnNames, tableName]);

    // Inline validation for distribution params
    const paramsValidation = useMemo((): ValidationResult => {
        const params = { min, max, values: choices.split(',').map(c => c.trim()).filter(Boolean) };
        return validateDistributionParams(type, distribution, params);
    }, [type, distribution, min, max, choices]);

    // Can save only if validation passes
    const canSave = nameValidation.isValid && paramsValidation.isValid;

    const handleSave = () => {
        if (!canSave) return;
        const distributionParams: Record<string, unknown> = { distribution };

        if (type === 'categorical') {
            distributionParams.choices = choices.split(',').map(c => c.trim()).filter(Boolean);
        } else if (type === 'int' || type === 'float') {
            if (distribution === 'uniform') {
                distributionParams.min = min;
                distributionParams.max = max;
            }
        } else if (type === 'foreign_key') {
            distributionParams.reference_table = refTable;
            distributionParams.reference_column = 'id';
        } else if (type === 'text') {
            // Add smart generation params for text columns
            distributionParams.smart_generate = smartGenerate;
            if (smartGenerate) {
                if (domainHint && domainHint !== 'custom') {
                    distributionParams.domain_hint = domainHint;
                }
                if (context) {
                    distributionParams.context = context;
                }
            }
        }

        updateColumn(tableId, column.id, {
            name,
            type,
            distributionParams,
        });

        onClose();
    };

    const handleDelete = () => {
        if (confirm(`Delete column "${column.name}"?`)) {
            removeColumn(tableId, column.id);
            onClose();
        }
    };

    return (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 animate-fade-in">
            <div className="card w-full max-w-md p-6 m-4 max-h-[90vh] overflow-y-auto">
                {/* Header */}
                <div className="flex items-center justify-between mb-6">
                    <h2 className="text-lg font-semibold text-white">Edit Column</h2>
                    <button
                        onClick={onClose}
                        className="text-zinc-500 hover:text-white transition-colors"
                    >
                        ✕
                    </button>
                </div>

                {/* Column Name */}
                <div className="mb-4">
                    <label className="block text-sm text-zinc-400 mb-2">Column Name</label>
                    <input
                        type="text"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        className={`input ${!nameValidation.isValid ? 'border-red-500 focus:ring-red-500/30' : nameValidation.warning ? 'border-yellow-500 focus:ring-yellow-500/30' : ''}`}
                        placeholder="column_name"
                    />
                    {/* Validation message for column name */}
                    {!nameValidation.isValid && (
                        <div className="flex items-center gap-1.5 mt-2 text-red-400 text-xs">
                            <AlertCircle className="w-3 h-3 flex-shrink-0" />
                            <span>{nameValidation.error}</span>
                        </div>
                    )}
                    {nameValidation.warning && (
                        <div className="flex items-center gap-1.5 mt-2 text-yellow-400 text-xs">
                            <AlertTriangle className="w-3 h-3 flex-shrink-0" />
                            <span>{nameValidation.warning}</span>
                        </div>
                    )}
                </div>

                {/* Column Type */}
                <div className="mb-4">
                    <label className="block text-sm text-zinc-400 mb-2">Data Type</label>
                    <div className="grid grid-cols-4 gap-2">
                        {columnTypes.map((ct) => (
                            <button
                                key={ct.value}
                                onClick={() => {
                                    setType(ct.value as Column['type']);
                                    setDistribution(distributions[ct.value as keyof typeof distributions][0]);
                                }}
                                className={`p-2 rounded-lg text-center transition-all ${type === ct.value
                                    ? 'bg-violet-600/20 border border-violet-600 text-violet-400'
                                    : 'bg-zinc-800 border border-zinc-700 text-zinc-400 hover:border-zinc-600'
                                    }`}
                            >
                                <div className="text-lg mb-1">{ct.icon}</div>
                                <div className="text-xs">{ct.label}</div>
                            </button>
                        ))}
                    </div>
                </div>

                {/* Distribution */}
                <div className="mb-4">
                    <label className="block text-sm text-zinc-400 mb-2">Distribution</label>
                    <select
                        value={distribution}
                        onChange={(e) => setDistribution(e.target.value)}
                        className="input"
                    >
                        {distributions[type]?.map((d) => (
                            <option key={d} value={d}>{d}</option>
                        ))}
                    </select>
                </div>

                {/* Smart Generation Controls for Text columns */}
                {type === 'text' && (
                    <div className="mb-4 p-4 rounded-lg bg-gradient-to-r from-violet-500/10 to-fuchsia-500/10 border border-violet-500/30">
                        <div className="flex items-center justify-between mb-3">
                            <div className="flex items-center gap-2">
                                <Sparkles className="w-4 h-4 text-violet-400" />
                                <span className="text-sm font-medium text-violet-300">Smart Generation</span>
                            </div>
                            <button
                                onClick={() => setSmartGenerate(!smartGenerate)}
                                className={`w-12 h-6 rounded-full transition-colors relative ${smartGenerate
                                    ? 'bg-violet-600'
                                    : 'bg-zinc-700'
                                    }`}
                            >
                                <div className={`w-5 h-5 rounded-full bg-white absolute top-0.5 transition-transform ${smartGenerate ? 'translate-x-6' : 'translate-x-0.5'
                                    }`} />
                            </button>
                        </div>

                        {smartGenerate && (
                            <div className="space-y-3 mt-3 pt-3 border-t border-violet-500/20">
                                <p className="text-xs text-zinc-400 flex items-center gap-1">
                                    <Brain className="w-3 h-3" />
                                    Uses LLM to generate realistic domain-specific values
                                </p>

                                <div>
                                    <label className="block text-xs text-zinc-400 mb-1.5">Domain</label>
                                    <select
                                        value={domainHint}
                                        onChange={(e) => setDomainHint(e.target.value)}
                                        className="input text-sm"
                                    >
                                        {smartDomains.map((d) => (
                                            <option key={d.value} value={d.value}>{d.label}</option>
                                        ))}
                                    </select>
                                </div>

                                {(domainHint === 'custom' || domainHint === '') && (
                                    <div>
                                        <label className="block text-xs text-zinc-400 mb-1.5">
                                            {domainHint === 'custom' ? 'Custom Context' : 'Additional Context (optional)'}
                                        </label>
                                        <input
                                            type="text"
                                            value={context}
                                            onChange={(e) => setContext(e.target.value)}
                                            className="input text-sm"
                                            placeholder={domainHint === 'custom'
                                                ? "e.g., 'startup SaaS company job titles'"
                                                : "e.g., 'emergency room setting'"
                                            }
                                        />
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                )}

                {/* Type-specific Parameters */}
                {type === 'categorical' && (
                    <div className="mb-4">
                        <label className="block text-sm text-zinc-400 mb-2">
                            Choices (comma-separated)
                        </label>
                        <input
                            type="text"
                            value={choices}
                            onChange={(e) => setChoices(e.target.value)}
                            className="input"
                            placeholder="red, blue, green"
                        />
                    </div>
                )}

                {(type === 'int' || type === 'float') && distribution === 'uniform' && (
                    <div className="grid grid-cols-2 gap-4 mb-4">
                        <div>
                            <label className="block text-sm text-zinc-400 mb-2">Min</label>
                            <input
                                type="number"
                                value={min}
                                onChange={(e) => setMin(Number(e.target.value))}
                                className="input"
                            />
                        </div>
                        <div>
                            <label className="block text-sm text-zinc-400 mb-2">Max</label>
                            <input
                                type="number"
                                value={max}
                                onChange={(e) => setMax(Number(e.target.value))}
                                className="input"
                            />
                        </div>
                    </div>
                )}

                {type === 'foreign_key' && (
                    <div className="mb-4">
                        <label className="block text-sm text-zinc-400 mb-2">Reference Table</label>
                        <select
                            value={refTable}
                            onChange={(e) => setRefTable(e.target.value)}
                            className="input"
                        >
                            <option value="">Select table...</option>
                            {tables
                                .filter(t => t.id !== tableId)
                                .map((t) => (
                                    <option key={t.id} value={t.name}>{t.name}</option>
                                ))}
                        </select>
                    </div>
                )}

                {/* Actions */}
                <div className="flex items-center justify-between pt-4 border-t border-zinc-800">
                    <button
                        onClick={handleDelete}
                        className="btn bg-red-500/10 text-red-400 border border-red-500/30 hover:bg-red-500/20"
                    >
                        Delete Column
                    </button>
                    <div className="flex gap-2">
                        <button onClick={onClose} className="btn btn-secondary">
                            Cancel
                        </button>
                        <button
                            onClick={handleSave}
                            disabled={!canSave}
                            className={`btn btn-primary ${!canSave ? 'opacity-50 cursor-not-allowed' : ''}`}
                            title={!canSave ? 'Fix validation errors to save' : 'Save changes'}
                        >
                            Save Changes
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}

