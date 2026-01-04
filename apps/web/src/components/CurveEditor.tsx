"use client";

import { useState, useCallback, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { X, TrendingUp, Calendar, DollarSign, BarChart3, Sparkles, Users, Heart, ShoppingCart, Activity } from 'lucide-react';
import { useSchemaStore, OutcomeConstraint, CurvePoint } from '@/store/schemaStore';

// Metric type detection from column name
type MetricType = 'money' | 'quantity' | 'users' | 'engagement' | 'rate' | 'generic';

interface MetricConfig {
    type: MetricType;
    label: string;
    unit: string;
    prefix: string;
    suffix: string;
    icon: typeof DollarSign;
    formatValue: (value: number) => string;
    formatShort: (value: number) => string;
    presets: Record<string, (periods: number) => number[]>;
    avgLabel: string;
}

function detectMetricType(columnName: string): MetricType {
    const name = columnName.toLowerCase();

    // Money/Revenue
    if (['revenue', 'mrr', 'arr', 'price', 'amount', 'total', 'sales', 'income', 'profit', 'cost', 'payment', 'transaction'].some(k => name.includes(k))) {
        return 'money';
    }

    // Users/Customers
    if (['users', 'customers', 'subscribers', 'members', 'signups', 'registrations', 'accounts'].some(k => name.includes(k))) {
        return 'users';
    }

    // Engagement (likes, views, shares)
    if (['likes', 'views', 'shares', 'comments', 'reactions', 'impressions', 'clicks', 'visits', 'sessions'].some(k => name.includes(k))) {
        return 'engagement';
    }

    // Rates (churn, conversion, retention)
    if (['rate', 'churn', 'conversion', 'retention', 'percentage', 'ratio'].some(k => name.includes(k))) {
        return 'rate';
    }

    // Quantity (orders, items, units)
    if (['quantity', 'orders', 'items', 'units', 'count', 'purchases', 'downloads', 'installs'].some(k => name.includes(k))) {
        return 'quantity';
    }

    return 'generic';
}

function getMetricConfig(metricType: MetricType, columnName: string): MetricConfig {
    const configs: Record<MetricType, MetricConfig> = {
        money: {
            type: 'money',
            label: 'Revenue Target',
            unit: 'USD',
            prefix: '$',
            suffix: '',
            icon: DollarSign,
            formatValue: (v) => `$${v.toLocaleString()}`,
            formatShort: (v) => v >= 1000 ? `$${(v / 1000).toFixed(1)}k` : `$${v}`,
            avgLabel: 'Avg Transaction ($)',
            presets: {
                'Linear Growth': (n) => Array.from({ length: n }, (_, i) => 100000 + (i * 10000)),
                'Seasonal': (n) => {
                    const base = [80, 85, 100, 110, 130, 150, 160, 155, 120, 100, 90, 95];
                    return Array.from({ length: n }, (_, i) => base[i % 12] * 1000);
                },
                'Hockey Stick': (n) => Array.from({ length: n }, (_, i) => Math.round(50000 * Math.pow(1.15, i))),
                'Flat': (n) => Array.from({ length: n }, () => 100000),
            },
        },
        users: {
            type: 'users',
            label: 'User Growth Target',
            unit: 'users',
            prefix: '',
            suffix: ' users',
            icon: Users,
            formatValue: (v) => `${v.toLocaleString()} users`,
            formatShort: (v) => v >= 1000 ? `${(v / 1000).toFixed(1)}k` : `${v}`,
            avgLabel: 'Avg Signups/Period',
            presets: {
                'Steady Growth': (n) => Array.from({ length: n }, (_, i) => 1000 + (i * 500)),
                'Viral Spike': (n) => Array.from({ length: n }, (_, i) => i === 5 ? 10000 : 1000 + (i * 200)),
                'S-Curve': (n) => Array.from({ length: n }, (_, i) => Math.round(10000 / (1 + Math.exp(-(i - n / 2))))),
                'Flat': (n) => Array.from({ length: n }, () => 2000),
            },
        },
        engagement: {
            type: 'engagement',
            label: `${columnName} Target`,
            unit: columnName.toLowerCase(),
            prefix: '',
            suffix: '',
            icon: Heart,
            formatValue: (v) => v.toLocaleString(),
            formatShort: (v) => v >= 1000000 ? `${(v / 1000000).toFixed(1)}M` : v >= 1000 ? `${(v / 1000).toFixed(1)}k` : `${v}`,
            avgLabel: 'Avg Per Item',
            presets: {
                'Steady Growth': (n) => Array.from({ length: n }, (_, i) => 50000 + (i * 10000)),
                'Viral Post': (n) => Array.from({ length: n }, (_, i) => i === 3 ? 500000 : 50000 + (i * 5000)),
                'Seasonal': (n) => {
                    const base = [80, 90, 100, 120, 110, 100, 90, 85, 100, 120, 140, 160];
                    return Array.from({ length: n }, (_, i) => base[i % 12] * 500);
                },
                'Flat': (n) => Array.from({ length: n }, () => 100000),
            },
        },
        rate: {
            type: 'rate',
            label: `${columnName} Target`,
            unit: '%',
            prefix: '',
            suffix: '%',
            icon: Activity,
            formatValue: (v) => `${v.toFixed(1)}%`,
            formatShort: (v) => `${v.toFixed(1)}%`,
            avgLabel: 'Base Rate (%)',
            presets: {
                'Improving': (n) => Array.from({ length: n }, (_, i) => Math.max(0, 5 - (i * 0.3))),
                'Worsening': (n) => Array.from({ length: n }, (_, i) => 2 + (i * 0.5)),
                'Stable': (n) => Array.from({ length: n }, () => 3),
                'Seasonal': (n) => {
                    const base = [3, 3.5, 4, 4.5, 5, 5.5, 5, 4.5, 4, 3.5, 3, 2.5];
                    return Array.from({ length: n }, (_, i) => base[i % 12]);
                },
            },
        },
        quantity: {
            type: 'quantity',
            label: `${columnName} Target`,
            unit: 'units',
            prefix: '',
            suffix: '',
            icon: ShoppingCart,
            formatValue: (v) => v.toLocaleString(),
            formatShort: (v) => v >= 1000 ? `${(v / 1000).toFixed(1)}k` : `${v}`,
            avgLabel: 'Avg Units/Transaction',
            presets: {
                'Steady Growth': (n) => Array.from({ length: n }, (_, i) => 5000 + (i * 500)),
                'Seasonal': (n) => {
                    const base = [80, 90, 100, 110, 120, 130, 120, 110, 100, 90, 100, 150];
                    return Array.from({ length: n }, (_, i) => base[i % 12] * 50);
                },
                'Flash Sale': (n) => Array.from({ length: n }, (_, i) => i === 11 ? 20000 : 5000 + (i * 300)),
                'Flat': (n) => Array.from({ length: n }, () => 5000),
            },
        },
        generic: {
            type: 'generic',
            label: `${columnName} Target`,
            unit: '',
            prefix: '',
            suffix: '',
            icon: BarChart3,
            formatValue: (v) => v.toLocaleString(),
            formatShort: (v) => v >= 1000 ? `${(v / 1000).toFixed(1)}k` : `${v}`,
            avgLabel: 'Avg Per Period',
            presets: {
                'Linear Growth': (n) => Array.from({ length: n }, (_, i) => 1000 + (i * 100)),
                'Exponential': (n) => Array.from({ length: n }, (_, i) => Math.round(1000 * Math.pow(1.1, i))),
                'Flat': (n) => Array.from({ length: n }, () => 1000),
            },
        },
    };

    return configs[metricType];
}

interface CurveEditorProps {
    constraint: OutcomeConstraint;
    tableName: string;
    columnName: string;
    onSave: (constraint: OutcomeConstraint) => void;
    onClose: () => void;
}

export default function CurveEditor({ constraint, tableName, columnName, onSave, onClose }: CurveEditorProps) {
    const [points, setPoints] = useState<CurvePoint[]>(constraint.curvePoints);
    const [timeUnit, setTimeUnit] = useState(constraint.timeUnit);
    const [avgTxn, setAvgTxn] = useState(constraint.avgTransactionValue || 50);

    // Detect metric type from column name
    const metricType = useMemo(() => detectMetricType(columnName), [columnName]);
    const metricConfig = useMemo(() => getMetricConfig(metricType, columnName), [metricType, columnName]);
    const MetricIcon = metricConfig.icon;

    // Generate month labels
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

    const maxValue = useMemo(() => Math.max(...points.map(p => p.value), 1), [points]);
    const totalValue = useMemo(() => points.reduce((sum, p) => sum + p.value, 0), [points]);

    const handlePreset = (presetName: string) => {
        const presetFn = metricConfig.presets[presetName];
        if (!presetFn) return;

        const values = presetFn(12);
        const baseDate = new Date();
        const newPoints = values.map((value, i) => ({
            timestamp: new Date(baseDate.getFullYear(), baseDate.getMonth() + i, 1).toISOString(),
            value: Math.round(value),
        }));
        setPoints(newPoints);
    };

    const handlePointChange = (index: number, value: number) => {
        const newPoints = [...points];
        newPoints[index] = { ...newPoints[index], value };
        setPoints(newPoints);
    };

    const handleSave = () => {
        onSave({
            ...constraint,
            curvePoints: points,
            timeUnit,
            avgTransactionValue: avgTxn,
        });
    };

    // Use Portal to render at document body level
    if (typeof document === 'undefined') return null;

    return createPortal(
        <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/40 backdrop-blur-sm" onClick={onClose}>
            <div
                className="w-[800px] max-h-[90vh] overflow-auto rounded-2xl shadow-2xl"
                style={{ background: '#FEFEFE', border: '1px solid rgba(58, 90, 64, 0.15)' }}
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header */}
                <div className="flex items-center justify-between p-6 border-b" style={{ borderColor: 'rgba(58, 90, 64, 0.1)' }}>
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: 'rgba(88, 129, 87, 0.15)' }}>
                            <MetricIcon className="w-5 h-5" style={{ color: '#3A5A40' }} />
                        </div>
                        <div>
                            <h2 className="text-lg font-semibold" style={{ color: '#3A5A40' }}>
                                {metricConfig.label}
                            </h2>
                            <p className="text-sm" style={{ color: '#6B7164' }}>
                                {tableName}.<span className="font-mono">{columnName}</span>
                            </p>
                        </div>
                    </div>
                    <button onClick={onClose} className="p-2 rounded-lg hover:bg-gray-100 transition">
                        <X className="w-5 h-5" style={{ color: '#6B7164' }} />
                    </button>
                </div>

                {/* Preset Buttons */}
                <div className="px-6 py-4 border-b" style={{ borderColor: 'rgba(58, 90, 64, 0.1)' }}>
                    <p className="text-xs uppercase tracking-wide mb-2" style={{ color: '#6B7164' }}>
                        Presets
                    </p>
                    <div className="flex gap-2 flex-wrap">
                        {Object.keys(metricConfig.presets).map((preset) => (
                            <button
                                key={preset}
                                onClick={() => handlePreset(preset)}
                                className="px-3 py-1.5 text-sm rounded-lg border transition hover:border-[#588157]"
                                style={{ borderColor: 'rgba(58, 90, 64, 0.2)', color: '#3A5A40' }}
                            >
                                {preset}
                            </button>
                        ))}
                    </div>
                </div>

                {/* Visual Curve Editor */}
                <div className="p-6">
                    <div
                        className="relative rounded-xl p-4"
                        style={{ background: 'rgba(218, 215, 205, 0.3)', border: '1px solid rgba(58, 90, 64, 0.1)', height: '280px' }}
                    >
                        {/* Y-axis labels - dynamic based on metric type */}
                        <div className="absolute left-2 top-4 bottom-10 w-16 flex flex-col justify-between text-right">
                            <span className="text-xs" style={{ color: '#6B7164' }}>{metricConfig.formatShort(maxValue)}</span>
                            <span className="text-xs" style={{ color: '#6B7164' }}>{metricConfig.formatShort(maxValue / 2)}</span>
                            <span className="text-xs" style={{ color: '#6B7164' }}>{metricConfig.prefix}0{metricConfig.suffix}</span>
                        </div>

                        {/* Bar Chart Container */}
                        <div
                            className="absolute left-20 right-4 top-4 bottom-10 flex items-end justify-between"
                            style={{ gap: '8px' }}
                        >
                            {points.map((point, i) => {
                                const heightPercent = maxValue > 0 ? (point.value / maxValue) * 100 : 0;
                                const barHeight = Math.max(8, (heightPercent / 100) * 200);

                                return (
                                    <div
                                        key={i}
                                        className="flex-1 flex flex-col items-center justify-end"
                                        style={{ height: '220px' }}
                                    >
                                        {/* The draggable bar */}
                                        <div
                                            className="w-full rounded-t cursor-ns-resize transition-all group relative"
                                            style={{
                                                height: `${barHeight}px`,
                                                minHeight: '8px',
                                                background: 'linear-gradient(180deg, #588157 0%, #3A5A40 100%)',
                                                boxShadow: '0 -2px 4px rgba(58, 90, 64, 0.2)',
                                                borderTop: '2px solid #6B8E6B'
                                            }}
                                            onMouseDown={(e) => {
                                                e.preventDefault();
                                                e.stopPropagation();
                                                const startY = e.clientY;
                                                const startValue = point.value;

                                                const handleMove = (moveEvent: MouseEvent) => {
                                                    const deltaY = startY - moveEvent.clientY;
                                                    const deltaValue = deltaY * (maxValue / 150);
                                                    const newValue = Math.max(0, Math.round(startValue + deltaValue));
                                                    handlePointChange(i, newValue);
                                                };

                                                const handleUp = () => {
                                                    document.removeEventListener('mousemove', handleMove);
                                                    document.removeEventListener('mouseup', handleUp);
                                                };

                                                document.addEventListener('mousemove', handleMove);
                                                document.addEventListener('mouseup', handleUp);
                                            }}
                                        >
                                            {/* Drag handle indicator */}
                                            <div className="absolute top-0 left-1/2 -translate-x-1/2 w-6 h-1.5 rounded bg-white/40 mt-1 opacity-0 group-hover:opacity-100 transition" />
                                            {/* Tooltip on hover - dynamic format */}
                                            <div className="absolute -top-10 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-gray-900 text-white text-xs px-2 py-1 rounded whitespace-nowrap pointer-events-none z-10">
                                                {metricConfig.formatShort(point.value)}
                                            </div>
                                        </div>
                                        {/* Month label */}
                                        <span className="text-[10px] mt-2 font-medium" style={{ color: '#6B7164' }}>
                                            {months[i % 12]}
                                        </span>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                </div>

                {/* Configuration */}
                <div className="px-6 py-4 grid grid-cols-3 gap-4 border-t" style={{ borderColor: 'rgba(58, 90, 64, 0.1)' }}>
                    <div>
                        <label className="text-xs uppercase tracking-wide mb-1 block" style={{ color: '#6B7164' }}>
                            Time Unit
                        </label>
                        <select
                            value={timeUnit}
                            onChange={(e) => setTimeUnit(e.target.value as OutcomeConstraint['timeUnit'])}
                            className="w-full px-3 py-2 rounded-lg border text-sm"
                            style={{ borderColor: 'rgba(58, 90, 64, 0.2)' }}
                        >
                            <option value="day">Daily</option>
                            <option value="week">Weekly</option>
                            <option value="month">Monthly</option>
                            <option value="quarter">Quarterly</option>
                        </select>
                    </div>
                    <div>
                        <label className="text-xs uppercase tracking-wide mb-1 block" style={{ color: '#6B7164' }}>
                            {metricConfig.avgLabel}
                        </label>
                        <input
                            type="number"
                            value={avgTxn}
                            onChange={(e) => setAvgTxn(Number(e.target.value))}
                            className="w-full px-3 py-2 rounded-lg border text-sm"
                            style={{ borderColor: 'rgba(58, 90, 64, 0.2)' }}
                        />
                    </div>
                    <div>
                        <label className="text-xs uppercase tracking-wide mb-1 block" style={{ color: '#6B7164' }}>
                            Total Target
                        </label>
                        <div className="px-3 py-2 rounded-lg text-sm font-semibold" style={{ background: 'rgba(88, 129, 87, 0.1)', color: '#3A5A40' }}>
                            {metricConfig.formatShort(totalValue)}
                        </div>
                    </div>
                </div>

                {/* Footer */}
                <div className="flex items-center justify-between p-6 border-t" style={{ borderColor: 'rgba(58, 90, 64, 0.1)' }}>
                    <p className="text-xs" style={{ color: '#6B7164' }}>
                        <Sparkles className="w-3 h-3 inline mr-1" />
                        The generator will create data that sums to this curve
                    </p>
                    <div className="flex gap-2">
                        <button
                            onClick={onClose}
                            className="px-4 py-2 text-sm rounded-lg border transition hover:bg-gray-50"
                            style={{ borderColor: 'rgba(58, 90, 64, 0.2)', color: '#3A5A40' }}
                        >
                            Cancel
                        </button>
                        <button
                            onClick={handleSave}
                            className="px-4 py-2 text-sm rounded-lg text-white font-medium transition"
                            style={{ background: 'linear-gradient(135deg, #588157 0%, #3A5A40 100%)' }}
                        >
                            Apply Constraint
                        </button>
                    </div>
                </div>
            </div>
        </div>,
        document.body
    );
}
