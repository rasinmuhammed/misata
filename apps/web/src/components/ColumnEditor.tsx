"use client";

import { useState, useEffect, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { Column, useSchemaStore } from '@/store/schemaStore';
import { validateColumnName, validateDistributionParams, ValidationResult } from '@/lib/validation';
import {
    X,
    Hash,
    Type,
    Calendar,
    List,
    ToggleLeft,
    Link2,
    AlertCircle,
    AlertTriangle,
    TrendingUp,
    Save,
    Trash2
} from 'lucide-react';

interface ColumnEditorProps {
    tableId: string;
    column: Column;
    onClose: () => void;
    onOpenCurveEditor?: () => void;
}

const columnTypes = [
    { value: 'int', label: 'Integer', icon: Hash, color: '#5B8A8A' },
    { value: 'float', label: 'Float', icon: Hash, color: '#7A9A7A' },
    { value: 'text', label: 'Text', icon: Type, color: '#588157' },
    { value: 'date', label: 'Date', icon: Calendar, color: '#D4A574' },
    { value: 'categorical', label: 'Categorical', icon: List, color: '#A3B18A' },
    { value: 'boolean', label: 'Boolean', icon: ToggleLeft, color: '#8B7355' },
    { value: 'foreign_key', label: 'Foreign Key', icon: Link2, color: '#3A5A40' },
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

export default function ColumnEditor({ tableId, column, onClose, onOpenCurveEditor }: ColumnEditorProps) {
    const { updateColumn, removeColumn, tables, getConstraintForColumn } = useSchemaStore();

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

    // Get current table for validation
    const currentTable = tables.find(t => t.id === tableId);
    const tableName = currentTable?.name || '';
    const existingColumnNames = (currentTable?.columns || [])
        .filter(c => c.id !== column.id)
        .map(c => c.name);

    // Check if this column has an outcome constraint
    const hasConstraint = getConstraintForColumn(column.id);
    const isNumeric = type === 'int' || type === 'float';

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

    const handleOpenCurveEditor = () => {
        onClose();
        if (onOpenCurveEditor) {
            onOpenCurveEditor();
        }
    };

    // Use Portal to render at document body level (escapes TableNode container)
    if (typeof document === 'undefined') return null;

    return createPortal(
        <div
            className="fixed inset-0 z-[9999] flex items-center justify-center"
            style={{ background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(4px)' }}
            onClick={onClose}
        >
            <div
                className="w-full max-w-2xl mx-4 rounded-2xl shadow-2xl overflow-hidden max-h-[90vh] flex flex-col"
                style={{ background: '#FEFEFE', border: '1px solid rgba(58, 90, 64, 0.15)' }}
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header */}
                <div
                    className="flex items-center justify-between px-6 py-4"
                    style={{ background: '#3A5A40' }}
                >
                    <h2 className="text-lg font-semibold text-white">Edit Column</h2>
                    <button
                        onClick={onClose}
                        className="p-1.5 rounded-lg hover:bg-white/10 transition text-white/80 hover:text-white"
                    >
                        <X className="w-5 h-5" />
                    </button>
                </div>

                <div className="p-6 space-y-5 flex-1 overflow-y-auto">
                    {/* Column Name */}
                    <div>
                        <label className="block text-sm font-medium mb-2" style={{ color: '#3A5A40' }}>
                            Column Name
                        </label>
                        <input
                            type="text"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            className="w-full px-4 py-2.5 rounded-lg border text-sm"
                            style={{
                                borderColor: !nameValidation.isValid ? '#EF4444' : 'rgba(58, 90, 64, 0.2)',
                                background: '#F5F3EF'
                            }}
                            placeholder="column_name"
                        />
                        {!nameValidation.isValid && (
                            <div className="flex items-center gap-1.5 mt-2 text-red-500 text-xs">
                                <AlertCircle className="w-3 h-3" />
                                <span>{nameValidation.error}</span>
                            </div>
                        )}
                        {nameValidation.warning && (
                            <div className="flex items-center gap-1.5 mt-2 text-amber-600 text-xs">
                                <AlertTriangle className="w-3 h-3" />
                                <span>{nameValidation.warning}</span>
                            </div>
                        )}
                    </div>

                    {/* Column Type */}
                    <div>
                        <label className="block text-sm font-medium mb-2" style={{ color: '#3A5A40' }}>
                            Data Type
                        </label>
                        <div className="grid grid-cols-4 gap-2">
                            {columnTypes.map((ct) => {
                                const Icon = ct.icon;
                                return (
                                    <button
                                        key={ct.value}
                                        onClick={() => {
                                            setType(ct.value as Column['type']);
                                            setDistribution(distributions[ct.value as keyof typeof distributions][0]);
                                        }}
                                        className="p-3 rounded-xl text-center transition-all border"
                                        style={{
                                            background: type === ct.value ? `${ct.color}15` : '#F5F3EF',
                                            borderColor: type === ct.value ? ct.color : 'transparent',
                                        }}
                                    >
                                        <div
                                            className="w-8 h-8 rounded-lg mx-auto mb-1.5 flex items-center justify-center"
                                            style={{ background: ct.color }}
                                        >
                                            <Icon className="w-4 h-4 text-white" />
                                        </div>
                                        <div className="text-xs font-medium" style={{ color: '#3A5A40' }}>
                                            {ct.label}
                                        </div>
                                    </button>
                                );
                            })}
                        </div>
                    </div>

                    {/* Distribution */}
                    <div>
                        <label className="block text-sm font-medium mb-2" style={{ color: '#3A5A40' }}>
                            Distribution
                        </label>
                        <select
                            value={distribution}
                            onChange={(e) => setDistribution(e.target.value)}
                            className="w-full px-4 py-2.5 rounded-lg border text-sm"
                            style={{ borderColor: 'rgba(58, 90, 64, 0.2)', background: '#F5F3EF' }}
                        >
                            {distributions[type]?.map((d) => (
                                <option key={d} value={d}>{d}</option>
                            ))}
                        </select>
                    </div>

                    {/* Outcome Constraint Button (for numeric columns) */}
                    {isNumeric && (
                        <div
                            className="p-4 rounded-xl border"
                            style={{
                                background: hasConstraint ? 'rgba(88, 129, 87, 0.1)' : '#F5F3EF',
                                borderColor: hasConstraint ? '#588157' : 'rgba(58, 90, 64, 0.15)'
                            }}
                        >
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                    <div
                                        className="w-10 h-10 rounded-lg flex items-center justify-center"
                                        style={{ background: hasConstraint ? '#588157' : 'rgba(58, 90, 64, 0.15)' }}
                                    >
                                        <TrendingUp className="w-5 h-5" style={{ color: hasConstraint ? '#FFF' : '#3A5A40' }} />
                                    </div>
                                    <div>
                                        <p className="text-sm font-medium" style={{ color: '#3A5A40' }}>
                                            Outcome Constraint
                                        </p>
                                        <p className="text-xs" style={{ color: '#6B7164' }}>
                                            {hasConstraint ? 'Curve applied - click to edit' : 'Draw a revenue/outcome curve'}
                                        </p>
                                    </div>
                                </div>
                                <button
                                    onClick={handleOpenCurveEditor}
                                    className="px-4 py-2 text-sm font-medium rounded-lg transition"
                                    style={{
                                        background: hasConstraint ? '#588157' : 'rgba(58, 90, 64, 0.15)',
                                        color: hasConstraint ? '#FFF' : '#3A5A40'
                                    }}
                                >
                                    {hasConstraint ? 'Edit Curve' : 'Add Curve'}
                                </button>
                            </div>
                        </div>
                    )}

                    {/* Type-specific Parameters */}
                    {type === 'categorical' && (
                        <div>
                            <label className="block text-sm font-medium mb-2" style={{ color: '#3A5A40' }}>
                                Choices (comma-separated)
                            </label>
                            <input
                                type="text"
                                value={choices}
                                onChange={(e) => setChoices(e.target.value)}
                                className="w-full px-4 py-2.5 rounded-lg border text-sm"
                                style={{ borderColor: 'rgba(58, 90, 64, 0.2)', background: '#F5F3EF' }}
                                placeholder="red, blue, green"
                            />
                        </div>
                    )}

                    {(type === 'int' || type === 'float') && distribution === 'uniform' && (
                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <label className="block text-sm font-medium mb-2" style={{ color: '#3A5A40' }}>Min</label>
                                <input
                                    type="number"
                                    value={min}
                                    onChange={(e) => setMin(Number(e.target.value))}
                                    className="w-full px-4 py-2.5 rounded-lg border text-sm"
                                    style={{ borderColor: 'rgba(58, 90, 64, 0.2)', background: '#F5F3EF' }}
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium mb-2" style={{ color: '#3A5A40' }}>Max</label>
                                <input
                                    type="number"
                                    value={max}
                                    onChange={(e) => setMax(Number(e.target.value))}
                                    className="w-full px-4 py-2.5 rounded-lg border text-sm"
                                    style={{ borderColor: 'rgba(58, 90, 64, 0.2)', background: '#F5F3EF' }}
                                />
                            </div>
                        </div>
                    )}

                    {type === 'foreign_key' && (
                        <div>
                            <label className="block text-sm font-medium mb-2" style={{ color: '#3A5A40' }}>
                                Reference Table
                            </label>
                            <select
                                value={refTable}
                                onChange={(e) => setRefTable(e.target.value)}
                                className="w-full px-4 py-2.5 rounded-lg border text-sm"
                                style={{ borderColor: 'rgba(58, 90, 64, 0.2)', background: '#F5F3EF' }}
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
                </div>

                {/* Actions */}
                <div
                    className="flex items-center justify-between px-6 py-4"
                    style={{ borderTop: '1px solid rgba(58, 90, 64, 0.1)', background: '#F5F3EF' }}
                >
                    <button
                        onClick={handleDelete}
                        className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition text-red-600 hover:bg-red-50"
                    >
                        <Trash2 className="w-4 h-4" />
                        Delete
                    </button>
                    <div className="flex gap-2">
                        <button
                            onClick={onClose}
                            className="px-4 py-2 text-sm font-medium rounded-lg border transition hover:bg-white"
                            style={{ borderColor: 'rgba(58, 90, 64, 0.2)', color: '#3A5A40' }}
                        >
                            Cancel
                        </button>
                        <button
                            onClick={handleSave}
                            disabled={!canSave}
                            className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg text-white transition"
                            style={{
                                background: canSave ? '#588157' : '#A3B18A',
                                opacity: canSave ? 1 : 0.6,
                                cursor: canSave ? 'pointer' : 'not-allowed'
                            }}
                        >
                            <Save className="w-4 h-4" />
                            Save
                        </button>
                    </div>
                </div>
            </div>
        </div>,
        document.body
    );
}
