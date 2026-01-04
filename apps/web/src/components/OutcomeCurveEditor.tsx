"use client";

import { useState, useCallback } from 'react';
import { X, TrendingUp, Zap, LineChart, Target, Sparkles } from 'lucide-react';
import { useSchemaStore, OutcomeConstraint, CurvePoint } from '@/store/schemaStore';

// Curve presets matching backend (outcome_curve.py get_curve_presets())
const CURVE_PRESETS: Record<string, { name: string; values: number[]; icon: typeof TrendingUp; color: string; description: string }> = {
    'linear_growth': {
        name: 'Linear Growth',
        values: [100, 120, 140, 160, 180, 200, 220, 240, 260, 280, 300, 320],
        icon: TrendingUp,
        color: 'var(--success)',
        description: 'Steady, predictable growth'
    },
    'hockey_stick': {
        name: 'Hockey Stick',
        values: [100, 102, 105, 108, 112, 118, 140, 180, 250, 350, 500, 700],
        icon: Zap,
        color: 'var(--accent-aurora)',
        description: 'Slow start, explosive growth'
    },
    'v_shaped_recovery': {
        name: 'V-shaped Recovery',
        values: [100, 80, 60, 50, 45, 50, 65, 85, 110, 140, 170, 200],
        icon: LineChart,
        color: 'var(--warning)',
        description: 'Dip then strong recovery'
    },
    'seasonal_retail': {
        name: 'Seasonal (Retail)',
        values: [100, 80, 70, 90, 100, 120, 110, 100, 130, 160, 200, 300],
        icon: Target,
        color: 'var(--info)',
        description: 'Holiday spike pattern'
    },
    'saas_growth': {
        name: 'SaaS Growth',
        values: [10, 18, 30, 50, 80, 120, 170, 230, 300, 380, 470, 570],
        icon: Sparkles,
        color: 'var(--accent-nebula)',
        description: 'Compound MRR growth'
    },
    'churn_decline': {
        name: 'Churn Decline',
        values: [1000, 920, 850, 790, 740, 700, 665, 635, 610, 590, 575, 560],
        icon: TrendingUp,
        color: 'var(--error)',
        description: 'Declining with stabilization'
    },
};

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

interface OutcomeCurveEditorProps {
    isOpen: boolean;
    onClose: () => void;
    tableId: string;
    columnId: string;
    tableName: string;
    columnName: string;
}

export default function OutcomeCurveEditor({
    isOpen,
    onClose,
    tableId,
    columnId,
    tableName,
    columnName,
}: OutcomeCurveEditorProps) {
    const { addOrUpdateConstraint, getConstraintForColumn, removeConstraint } = useSchemaStore();

    const existingConstraint = getConstraintForColumn(columnId);

    const [selectedPreset, setSelectedPreset] = useState<string | null>(
        existingConstraint ? null : 'hockey_stick'
    );
    const [values, setValues] = useState<number[]>(
        existingConstraint
            ? existingConstraint.curvePoints.map(p => p.value)
            : CURVE_PRESETS['hockey_stick'].values
    );
    const [scaleFactor, setScaleFactor] = useState(1000);
    const [editingIndex, setEditingIndex] = useState<number | null>(null);

    const handlePresetSelect = useCallback((presetKey: string) => {
        setSelectedPreset(presetKey);
        setValues([...CURVE_PRESETS[presetKey].values]);
    }, []);

    const handleValueChange = useCallback((index: number, newValue: number) => {
        setValues(prev => {
            const updated = [...prev];
            updated[index] = Math.max(0, newValue);
            return updated;
        });
        setSelectedPreset(null); // Custom values
    }, []);

    const handleSave = useCallback(() => {
        // Generate curve points with timestamps (monthly, starting from current year)
        const year = new Date().getFullYear();
        const curvePoints: CurvePoint[] = values.map((value, i) => ({
            timestamp: new Date(year, i, 1).toISOString(),
            value: value * scaleFactor,
        }));

        const constraint: OutcomeConstraint = {
            id: existingConstraint?.id || `constraint_${Date.now()}`,
            tableId,
            columnId,
            curvePoints,
            timeUnit: 'month',
            avgTransactionValue: 50,
        };

        addOrUpdateConstraint(constraint);
        onClose();
    }, [values, scaleFactor, tableId, columnId, existingConstraint, addOrUpdateConstraint, onClose]);

    const handleRemove = useCallback(() => {
        if (existingConstraint) {
            removeConstraint(existingConstraint.id);
        }
        onClose();
    }, [existingConstraint, removeConstraint, onClose]);

    if (!isOpen) return null;

    const maxValue = Math.max(...values);
    const scaledTotal = values.reduce((sum, v) => sum + v * scaleFactor, 0);

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.6)' }}>
            <div className="w-full max-w-4xl max-h-[90vh] overflow-y-auto rounded-xl shadow-2xl" style={{ background: 'var(--bg-primary)' }}>
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--border-subtle)]">
                    <div>
                        <h2 className="text-lg font-semibold text-[var(--text-primary)]">
                            Outcome Constraint
                        </h2>
                        <p className="text-sm text-[var(--text-muted)]">
                            Define the target curve for <span className="font-mono">{tableName}.{columnName}</span>
                        </p>
                    </div>
                    <button onClick={onClose} className="p-2 rounded-lg hover:bg-[var(--surface-subtle)]">
                        <X className="w-5 h-5 text-[var(--text-muted)]" />
                    </button>
                </div>

                <div className="p-6 space-y-6">
                    {/* Preset Grid */}
                    <div>
                        <h3 className="text-sm font-medium text-[var(--text-secondary)] mb-3">Select a Curve Pattern</h3>
                        <div className="grid grid-cols-3 gap-3">
                            {Object.entries(CURVE_PRESETS).map(([key, preset]) => {
                                const Icon = preset.icon;
                                const isSelected = selectedPreset === key;
                                return (
                                    <button
                                        key={key}
                                        onClick={() => handlePresetSelect(key)}
                                        className={`p-4 rounded-lg border-2 text-left transition-all ${isSelected
                                                ? 'border-[var(--brand-primary)] bg-[var(--brand-primary)]/10'
                                                : 'border-[var(--border-subtle)] hover:border-[var(--border-default)]'
                                            }`}
                                    >
                                        <div className="flex items-center gap-2 mb-1">
                                            <Icon className="w-4 h-4" style={{ color: preset.color }} />
                                            <span className="font-medium text-[var(--text-primary)]">{preset.name}</span>
                                        </div>
                                        <p className="text-xs text-[var(--text-muted)]">{preset.description}</p>
                                        {/* Mini sparkline */}
                                        <div className="flex items-end gap-0.5 h-6 mt-2">
                                            {preset.values.map((v, i) => (
                                                <div
                                                    key={i}
                                                    className="flex-1 rounded-sm"
                                                    style={{
                                                        height: `${(v / Math.max(...preset.values)) * 100}%`,
                                                        background: isSelected ? preset.color : 'var(--text-muted)',
                                                        opacity: isSelected ? 1 : 0.3,
                                                    }}
                                                />
                                            ))}
                                        </div>
                                    </button>
                                );
                            })}
                        </div>
                    </div>

                    {/* Interactive Chart */}
                    <div>
                        <div className="flex items-center justify-between mb-3">
                            <h3 className="text-sm font-medium text-[var(--text-secondary)]">Monthly Values</h3>
                            <div className="flex items-center gap-2">
                                <span className="text-xs text-[var(--text-muted)]">Scale:</span>
                                <select
                                    value={scaleFactor}
                                    onChange={(e) => setScaleFactor(Number(e.target.value))}
                                    className="text-xs px-2 py-1 rounded border border-[var(--border-subtle)] bg-[var(--bg-secondary)]"
                                >
                                    <option value={1}>×1</option>
                                    <option value={10}>×10</option>
                                    <option value={100}>×100</option>
                                    <option value={1000}>×1,000</option>
                                    <option value={10000}>×10,000</option>
                                </select>
                            </div>
                        </div>

                        {/* Bar Chart */}
                        <div className="bg-[var(--bg-secondary)] rounded-lg p-4 border border-[var(--border-subtle)]">
                            <div className="flex items-end justify-between h-48 gap-2">
                                {values.map((value, i) => (
                                    <div key={i} className="flex-1 flex flex-col items-center">
                                        <div className="relative w-full flex flex-col items-center" style={{ height: '160px' }}>
                                            {/* Bar */}
                                            <div
                                                className="absolute bottom-0 w-full rounded-t cursor-pointer hover:opacity-80 transition-opacity"
                                                style={{
                                                    height: `${(value / maxValue) * 100}%`,
                                                    background: selectedPreset
                                                        ? CURVE_PRESETS[selectedPreset]?.color || 'var(--brand-primary)'
                                                        : 'var(--brand-primary)',
                                                    minHeight: '4px',
                                                }}
                                                onClick={() => setEditingIndex(i)}
                                            />
                                            {/* Value label */}
                                            {editingIndex === i ? (
                                                <input
                                                    type="number"
                                                    value={value}
                                                    onChange={(e) => handleValueChange(i, Number(e.target.value))}
                                                    onBlur={() => setEditingIndex(null)}
                                                    onKeyDown={(e) => e.key === 'Enter' && setEditingIndex(null)}
                                                    autoFocus
                                                    className="absolute -top-6 w-12 text-xs text-center bg-[var(--bg-primary)] border border-[var(--border-default)] rounded px-1"
                                                />
                                            ) : (
                                                <span
                                                    className="absolute -top-5 text-xs text-[var(--text-muted)] cursor-pointer"
                                                    onClick={() => setEditingIndex(i)}
                                                >
                                                    {value}
                                                </span>
                                            )}
                                        </div>
                                        <span className="text-xs text-[var(--text-muted)] mt-2">{MONTHS[i]}</span>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Summary */}
                        <div className="flex items-center justify-between mt-3 px-2">
                            <span className="text-xs text-[var(--text-muted)]">
                                Total Annual: <span className="font-semibold text-[var(--text-primary)]">
                                    ${scaledTotal.toLocaleString()}
                                </span>
                            </span>
                            <span className="text-xs text-[var(--text-muted)]">
                                Click bars to edit values
                            </span>
                        </div>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center justify-between pt-4 border-t border-[var(--border-subtle)]">
                        <div>
                            {existingConstraint && (
                                <button
                                    onClick={handleRemove}
                                    className="text-sm text-[var(--error)] hover:underline"
                                >
                                    Remove Constraint
                                </button>
                            )}
                        </div>
                        <div className="flex gap-3">
                            <button onClick={onClose} className="btn btn-ghost">
                                Cancel
                            </button>
                            <button onClick={handleSave} className="btn btn-primary">
                                <Target className="w-4 h-4" />
                                Apply Constraint
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
