"use client";

import { useState } from 'react';
import {
    X,
    BarChart3,
    AlertTriangle,
    CheckCircle,
    TrendingUp,
    Database,
    Table2,
    AlertCircle,
    ChevronDown,
    ChevronRight,
} from 'lucide-react';
import {
    LineChart,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
    Area,
    AreaChart
} from 'recharts';

interface ColumnStats {
    dtype: string;
    null_count: number;
    null_pct: number;
    unique_count: number;
    cardinality_pct: number;
    min?: number;
    max?: number;
    mean?: number;
    std?: number;
    median?: number;
    histogram?: {
        counts: number[];
        bin_edges: number[];
    };
    outliers?: {
        count: number;
        percentage: number;
        lower_bound: number;
        upper_bound: number;
    };
    value_distribution?: Record<string, { count: number; percentage: number }>;
    top_values?: Record<string, number>;
}

interface TableStats {
    row_count: number;
    column_count: number;
    file_size_kb: number;
    memory_usage_kb: number;
    columns: Record<string, ColumnStats>;
    correlations?: Record<string, Record<string, number>>;
    numeric_summary?: Record<string, {
        mean: number;
        std: number;
        min: number;
        "25%": number;
        "50%": number;
        "75%": number;
        max: number;
        skewness: number;
        kurtosis: number;
    }>;
}

interface QualityIssue {
    table: string;
    type: string;
    column?: string;
    columns?: string[];
    percentage?: number;
    value?: number;
    note?: string;
}

interface QualityReportData {
    job_id: string;
    generated_at: string;
    summary: {
        total_tables: number;
        total_rows: number;
        total_columns: number;
        quality_score: number;
        issues_count: number;
    };
    tables: Record<string, TableStats>;
    quality_issues: QualityIssue[];
    verification?: {
        match_score: number;
        expected: number[];
        actual: number[];
        error_pct: number[];
        avg_error_pct: number;
    };
}

interface QualityReportProps {
    report: QualityReportData | null;
    isOpen: boolean;
    onClose: () => void;
}

// Simple Histogram Bar Chart Component
function Histogram({ data }: { data: { counts: number[]; bin_edges: number[] } }) {
    const maxCount = Math.max(...data.counts);

    return (
        <div className="flex items-end gap-0.5 h-16">
            {data.counts.map((count, i) => (
                <div
                    key={i}
                    className="flex-1 bg-[var(--brand-primary)] rounded-t opacity-80 hover:opacity-100 transition-opacity"
                    style={{ height: `${(count / maxCount) * 100}%`, minHeight: count > 0 ? '2px' : '0' }}
                    title={`${data.bin_edges[i].toFixed(1)} - ${data.bin_edges[i + 1].toFixed(1)}: ${count}`}
                />
            ))}
        </div>
    );
}

// Quality Score Circle
function QualityScoreCircle({ score }: { score: number }) {
    const color = score >= 80 ? 'var(--success)' : score >= 60 ? 'var(--warning)' : 'var(--error)';
    const circumference = 2 * Math.PI * 40;
    const offset = circumference - (score / 100) * circumference;

    return (
        <div className="relative w-24 h-24">
            <svg className="w-24 h-24 transform -rotate-90">
                <circle
                    cx="48"
                    cy="48"
                    r="40"
                    stroke="var(--border-subtle)"
                    strokeWidth="8"
                    fill="none"
                />
                <circle
                    cx="48"
                    cy="48"
                    r="40"
                    stroke={color}
                    strokeWidth="8"
                    fill="none"
                    strokeDasharray={circumference}
                    strokeDashoffset={offset}
                    strokeLinecap="round"
                    className="transition-all duration-500"
                />
            </svg>
            <div className="absolute inset-0 flex items-center justify-center">
                <span className="text-2xl font-bold" style={{ color }}>{score}</span>
            </div>
        </div>
    );
}

// Value Distribution Bar
function ValueDistributionBar({ value, max, label, count }: { value: number; max: number; label: string; count: number }) {
    return (
        <div className="flex items-center gap-2 text-xs">
            <span className="w-24 truncate text-[var(--text-secondary)]" title={label}>{label}</span>
            <div className="flex-1 h-4 bg-[var(--bg-secondary)] rounded-full overflow-hidden">
                <div
                    className="h-full bg-[var(--brand-primary)] rounded-full"
                    style={{ width: `${(value / max) * 100}%` }}
                />
            </div>
            <span className="w-16 text-right text-[var(--text-muted)]">{count} ({value.toFixed(1)}%)</span>
        </div>
    );
}

// Helper for currency formatting
const formatCurrency = (val: number) => {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        maximumFractionDigits: 0
    }).format(val);
};

// Helper for automated insights
const getAutomatedInsights = (verification: QualityReportData['verification']) => {
    if (!verification) return [];

    const insights = [];
    const score = verification.match_score;
    const avgError = verification.avg_error_pct;

    // 1. Overall Match Insight
    if (score >= 90) {
        insights.push(`Strong verification! The generated data matches the expected revenue model with ${score}% accuracy.`);
    } else if (score >= 70) {
        insights.push(`Good match (${score}%), but some deviations detected (${avgError}% avg error).`);
    } else {
        insights.push(`Significant deviation from the requested model. Match score is only ${score}%.`);
    }

    // 2. Seasonality Insight (Peak/Low)
    const combinedData = verification.actual.map((val, i) => ({
        month: i + 1,
        actual: val,
        expected: verification.expected[i]
    }));

    const peak = combinedData.reduce((max, curr) => curr.actual > max.actual ? curr : max, combinedData[0]);
    const low = combinedData.reduce((min, curr) => curr.actual < min.actual ? curr : min, combinedData[0]);

    insights.push(`Revenue speaks to a seasonal trend, peaking in Month ${peak.month} (${formatCurrency(peak.actual)}) and dipping in Month ${low.month} (${formatCurrency(low.actual)}).`);

    return insights;
};

export default function QualityReport({ report, isOpen, onClose }: QualityReportProps) {
    const [expandedTables, setExpandedTables] = useState<Set<string>>(new Set());
    const [activeTab, setActiveTab] = useState<'overview' | 'tables' | 'issues'>('overview');

    if (!isOpen || !report) return null;

    const toggleTable = (tableName: string) => {
        const newExpanded = new Set(expandedTables);
        if (newExpanded.has(tableName)) {
            newExpanded.delete(tableName);
        } else {
            newExpanded.add(tableName);
        }
        setExpandedTables(newExpanded);
    };

    const getIssueIcon = (type: string) => {
        switch (type) {
            case 'high_nulls': return <AlertCircle className="w-4 h-4 text-[var(--warning)]" />;
            case 'high_correlation': return <TrendingUp className="w-4 h-4 text-[var(--info)]" />;
            case 'high_outliers': return <AlertTriangle className="w-4 h-4 text-[var(--error)]" />;
            case 'all_unique': return <Database className="w-4 h-4 text-[var(--text-muted)]" />;
            default: return <AlertCircle className="w-4 h-4 text-[var(--warning)]" />;
        }
    };

    const getIssueDescription = (issue: QualityIssue) => {
        switch (issue.type) {
            case 'high_nulls':
                return `${issue.column} has ${issue.percentage}% null values`;
            case 'high_correlation':
                return `${issue.columns?.join(' & ')} are ${(issue.value! * 100).toFixed(0)}% correlated`;
            case 'high_outliers':
                return `${issue.column} has ${issue.percentage}% outliers`;
            case 'all_unique':
                return `${issue.column}: ${issue.note}`;
            default:
                return issue.note || 'Unknown issue';
        }
    };

    return (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 animate-fade-in">
            <div className="card card-elevated w-full max-w-4xl max-h-[90vh] m-4 flex flex-col overflow-hidden">
                {/* Header */}
                <div className="flex items-center justify-between p-6 border-b border-[var(--border-subtle)]">
                    <div className="flex items-center gap-3">
                        {/* Revenue Model Verification (Automated EDA) */}
                        {report.verification && (
                            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden mb-6 w-full">
                                <div className="p-4 border-b border-gray-100 bg-gray-50 flex items-center justify-between">
                                    <div className="flex items-center gap-2">
                                        <div className={`p-1.5 rounded-md ${report.verification.match_score >= 80 ? 'bg-green-100 text-green-600' : 'bg-amber-100 text-amber-600'}`}>
                                            <TrendingUp className="w-4 h-4" />
                                        </div>
                                        <h3 className="font-semibold text-gray-800">Revenue Model Verification</h3>
                                    </div>
                                    {report.verification.match_score >= 90 && (
                                        <span className="text-xs bg-green-100 text-green-700 px-2.5 py-1 rounded-full font-medium border border-green-200">
                                            VERIFIED MODEL
                                        </span>
                                    )}
                                </div>

                                <div className="p-6">
                                    {/* 1. Key Metrics Row */}
                                    <div className="grid grid-cols-4 gap-4 mb-6">
                                        <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                            <div className="text-xs text-gray-500 font-medium uppercase tracking-wider mb-1">Match Score</div>
                                            <div className={`text-2xl font-bold ${report.verification.match_score >= 90 ? 'text-green-600' : 'text-amber-600'}`}>
                                                {report.verification.match_score}%
                                            </div>
                                        </div>
                                        <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                            <div className="text-xs text-gray-500 font-medium uppercase tracking-wider mb-1">Total Revenue</div>
                                            <div className="text-2xl font-bold text-gray-800">
                                                {formatCurrency(report.verification.actual.reduce((a, b) => a + b, 0))}
                                            </div>
                                        </div>
                                        <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                            <div className="text-xs text-gray-500 font-medium uppercase tracking-wider mb-1">Avg Deviation</div>
                                            <div className="text-2xl font-bold text-gray-800">
                                                {report.verification.avg_error_pct}%
                                            </div>
                                        </div>
                                        {/* Peak Month Calculation */}
                                        {(() => {
                                            const maxVal = Math.max(...report.verification.actual);
                                            const maxIdx = report.verification.actual.indexOf(maxVal);
                                            // Assuming monthly data starting Jan
                                            const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
                                            return (
                                                <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
                                                    <div className="text-xs text-gray-500 font-medium uppercase tracking-wider mb-1">Peak Month</div>
                                                    <div className="text-2xl font-bold text-gray-800">
                                                        {months[maxIdx % 12]}
                                                    </div>
                                                </div>
                                            );
                                        })()}
                                    </div>

                                    {/* 2. Interactive Chart */}
                                    <div className="h-[300px] w-full mb-6">
                                        <ResponsiveContainer width="100%" height="100%">
                                            <AreaChart
                                                data={report.verification.actual.map((val, i) => ({
                                                    month: `Month ${i + 1}`,
                                                    Actual: val,
                                                    Expected: report.verification?.expected[i] || 0
                                                }))}
                                                margin={{ top: 10, right: 30, left: 0, bottom: 0 }}
                                            >
                                                <defs>
                                                    <linearGradient id="colorActual" x1="0" y1="0" x2="0" y2="1">
                                                        <stop offset="5%" stopColor="#10b981" stopOpacity={0.1} />
                                                        <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                                                    </linearGradient>
                                                    <linearGradient id="colorExpected" x1="0" y1="0" x2="0" y2="1">
                                                        <stop offset="5%" stopColor="#6366f1" stopOpacity={0.1} />
                                                        <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                                                    </linearGradient>
                                                </defs>
                                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
                                                <XAxis dataKey="month" axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#6b7280' }} />
                                                <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: '#6b7280' }} tickFormatter={(val) => `$${val / 1000}k`} />
                                                <Tooltip
                                                    contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
                                                    formatter={(value: number | string | Array<number | string> | undefined) => {
                                                        if (value === undefined || value === null) return '';
                                                        const numVal = Number(value);
                                                        return isNaN(numVal) ? value : formatCurrency(numVal);
                                                    }}
                                                />
                                                <Legend wrapperStyle={{ paddingTop: '20px' }} />
                                                <Area
                                                    type="monotone"
                                                    dataKey="Expected"
                                                    stroke="#6366f1"
                                                    fillOpacity={1}
                                                    fill="url(#colorExpected)"
                                                    strokeWidth={2}
                                                    strokeDasharray="5 5"
                                                />
                                                <Area
                                                    type="monotone"
                                                    dataKey="Actual"
                                                    stroke="#10b981"
                                                    fillOpacity={1}
                                                    fill="url(#colorActual)"
                                                    strokeWidth={2}
                                                />
                                            </AreaChart>
                                        </ResponsiveContainer>
                                    </div>

                                    {/* 3. Automated Insights */}
                                    <div className="bg-blue-50/50 rounded-lg p-4 border border-blue-100">
                                        <h4 className="flex items-center gap-2 text-sm font-semibold text-blue-900 mb-2">
                                            <div className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
                                            Automated Insights
                                        </h4>
                                        <ul className="space-y-1">
                                            {getAutomatedInsights(report.verification).map((insight, idx) => (
                                                <li key={idx} className="text-sm text-blue-800 leading-relaxed">
                                                    • {insight}
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                </div>
                            </div>
                        )}

                        <div className="w-10 h-10 rounded-lg bg-[var(--accent-muted)] flex items-center justify-center">
                            <BarChart3 className="w-5 h-5 text-[var(--brand-primary-light)]" />
                        </div>
                        <div>
                            <h2 className="text-title text-[var(--text-primary)]">Data Quality Report</h2>
                            <p className="text-xs text-[var(--text-muted)]">
                                Generated {new Date(report.generated_at).toLocaleString()}
                            </p>
                        </div>
                    </div>
                    <button
                        onClick={onClose}
                        className="btn btn-ghost btn-sm"
                    >
                        <X className="w-5 h-5" />
                    </button>
                </div >

                {/* Tabs */}
                < div className="flex gap-1 px-6 pt-4 border-b border-[var(--border-subtle)]" >
                    {(['overview', 'tables', 'issues'] as const).map((tab) => (
                        <button
                            key={tab}
                            onClick={() => setActiveTab(tab)}
                            className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${activeTab === tab
                                ? 'bg-[var(--bg-secondary)] text-[var(--text-primary)] border-b-2 border-[var(--brand-primary)]'
                                : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]'
                                }`}
                        >
                            {tab === 'overview' && 'Overview'}
                            {tab === 'tables' && `Tables (${report.summary.total_tables})`}
                            {tab === 'issues' && `Issues (${report.summary.issues_count})`}
                        </button>
                    ))
                    }
                </div >

                {/* Content */}
                < div className="flex-1 overflow-y-auto p-6" >
                    {/* Overview Tab */}
                    {
                        activeTab === 'overview' && (
                            <div className="space-y-6">
                                {/* Summary Cards */}
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                    <div className="card p-4 text-center">
                                        <QualityScoreCircle score={report.summary.quality_score} />
                                        <p className="text-xs text-[var(--text-muted)] mt-2">Quality Score</p>
                                    </div>
                                    <div className="card p-4">
                                        <div className="text-3xl font-bold text-[var(--brand-primary)]">
                                            {report.summary.total_tables}
                                        </div>
                                        <p className="text-xs text-[var(--text-muted)]">Tables</p>
                                        <div className="mt-2 text-sm text-[var(--text-secondary)]">
                                            {report.summary.total_columns} columns total
                                        </div>
                                    </div>
                                    <div className="card p-4">
                                        <div className="text-3xl font-bold text-[var(--success)]">
                                            {report.summary.total_rows.toLocaleString()}
                                        </div>
                                        <p className="text-xs text-[var(--text-muted)]">Total Rows</p>
                                    </div>
                                    <div className="card p-4">
                                        <div className="text-3xl font-bold text-[var(--warning)]">
                                            {report.summary.issues_count}
                                        </div>
                                        <p className="text-xs text-[var(--text-muted)]">Issues Found</p>
                                        {report.summary.issues_count === 0 && (
                                            <div className="flex items-center gap-1 mt-2 text-sm text-[var(--success)]">
                                                <CheckCircle className="w-4 h-4" />
                                                All clear
                                            </div>
                                        )}
                                    </div>
                                </div>

                                {/* Tables Overview */}
                                <div>
                                    <h3 className="text-sm font-medium text-[var(--text-secondary)] mb-3">Tables Overview</h3>
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                        {Object.entries(report.tables).map(([tableName, tableStats]) => {
                                            if (!tableStats || !tableStats.row_count) return null;
                                            return (
                                                <div key={tableName} className="card p-4">
                                                    <div className="flex items-center gap-2 mb-2">
                                                        <Table2 className="w-4 h-4 text-[var(--brand-primary)]" />
                                                        <span className="font-medium text-[var(--text-primary)]">{tableName}</span>
                                                    </div>
                                                    <div className="grid grid-cols-3 gap-2 text-xs text-[var(--text-muted)]">
                                                        <div>
                                                            <span className="text-[var(--text-secondary)] font-medium">
                                                                {tableStats.row_count?.toLocaleString() ?? 0}
                                                            </span> rows
                                                        </div>
                                                        <div>
                                                            <span className="text-[var(--text-secondary)] font-medium">
                                                                {tableStats.column_count ?? 0}
                                                            </span> cols
                                                        </div>
                                                        <div>
                                                            <span className="text-[var(--text-secondary)] font-medium">
                                                                {tableStats.file_size_kb ?? 0}
                                                            </span> KB
                                                        </div>
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>
                            </div>
                        )
                    }

                    {/* Tables Tab */}
                    {
                        activeTab === 'tables' && (
                            <div className="space-y-4">
                                {Object.entries(report.tables).map(([tableName, tableStats]) => {
                                    if (!tableStats || !tableStats.row_count) return null;
                                    return (
                                        <div key={tableName} className="card overflow-hidden">
                                            <button
                                                onClick={() => toggleTable(tableName)}
                                                className="w-full flex items-center justify-between p-4 hover:bg-[var(--bg-secondary)] transition-colors"
                                            >
                                                <div className="flex items-center gap-3">
                                                    {expandedTables.has(tableName) ? (
                                                        <ChevronDown className="w-5 h-5 text-[var(--text-muted)]" />
                                                    ) : (
                                                        <ChevronRight className="w-5 h-5 text-[var(--text-muted)]" />
                                                    )}
                                                    <Table2 className="w-5 h-5 text-[var(--brand-primary)]" />
                                                    <span className="font-medium text-[var(--text-primary)]">{tableName}</span>
                                                </div>
                                                <div className="flex items-center gap-4 text-sm text-[var(--text-muted)]">
                                                    <span>{tableStats.row_count?.toLocaleString() ?? 0} rows</span>
                                                    <span>{tableStats.column_count ?? 0} columns</span>
                                                </div>
                                            </button>

                                            {expandedTables.has(tableName) && (
                                                <div className="border-t border-[var(--border-subtle)] p-4 space-y-4">
                                                    {/* Column Details */}
                                                    <div className="space-y-3">
                                                        {Object.entries(tableStats.columns).map(([colName, colStats]) => (
                                                            <div key={colName} className="bg-[var(--bg-secondary)] rounded-lg p-3">
                                                                <div className="flex items-center justify-between mb-2">
                                                                    <span className="font-mono text-sm text-[var(--text-primary)]">{colName}</span>
                                                                    <span className="text-xs text-[var(--text-muted)] bg-[var(--bg-tertiary)] px-2 py-0.5 rounded">
                                                                        {colStats.dtype}
                                                                    </span>
                                                                </div>

                                                                <div className="grid grid-cols-4 gap-2 text-xs mb-2">
                                                                    <div>
                                                                        <span className="text-[var(--text-muted)]">Unique: </span>
                                                                        <span className="text-[var(--text-secondary)]">{colStats.unique_count}</span>
                                                                    </div>
                                                                    <div>
                                                                        <span className="text-[var(--text-muted)]">Nulls: </span>
                                                                        <span className={colStats.null_pct > 0 ? 'text-[var(--warning)]' : 'text-[var(--text-secondary)]'}>
                                                                            {colStats.null_pct}%
                                                                        </span>
                                                                    </div>
                                                                    {colStats.mean !== undefined && (
                                                                        <>
                                                                            <div>
                                                                                <span className="text-[var(--text-muted)]">Mean: </span>
                                                                                <span className="text-[var(--text-secondary)]">{colStats.mean}</span>
                                                                            </div>
                                                                            <div>
                                                                                <span className="text-[var(--text-muted)]">Range: </span>
                                                                                <span className="text-[var(--text-secondary)]">{colStats.min} - {colStats.max}</span>
                                                                            </div>
                                                                        </>
                                                                    )}
                                                                </div>

                                                                {/* Histogram for numeric columns */}
                                                                {colStats.histogram && (
                                                                    <div className="mt-2">
                                                                        <Histogram data={colStats.histogram} />
                                                                    </div>
                                                                )}

                                                                {/* Value distribution for categorical */}
                                                                {colStats.value_distribution && (
                                                                    <div className="mt-2 space-y-1">
                                                                        {Object.entries(colStats.value_distribution).slice(0, 5).map(([val, data]) => (
                                                                            <ValueDistributionBar
                                                                                key={val}
                                                                                label={val}
                                                                                value={data.percentage}
                                                                                count={data.count}
                                                                                max={Math.max(...Object.values(colStats.value_distribution!).map(v => v.percentage))}
                                                                            />
                                                                        ))}
                                                                    </div>
                                                                )}

                                                                {/* Outlier info */}
                                                                {colStats.outliers && colStats.outliers.count > 0 && (
                                                                    <div className="mt-2 flex items-center gap-2 text-xs text-[var(--warning)]">
                                                                        <AlertTriangle className="w-3 h-3" />
                                                                        {colStats.outliers.count} outliers ({colStats.outliers.percentage}%)
                                                                    </div>
                                                                )}
                                                            </div>
                                                        ))}
                                                    </div>

                                                    {/* Correlation Matrix */}
                                                    {tableStats.correlations && Object.keys(tableStats.correlations).length >= 2 && (
                                                        <div>
                                                            <h4 className="text-sm font-medium text-[var(--text-secondary)] mb-2">Correlations</h4>
                                                            <div className="overflow-x-auto">
                                                                <table className="text-xs w-full">
                                                                    <thead>
                                                                        <tr>
                                                                            <th className="p-1"></th>
                                                                            {Object.keys(tableStats.correlations).map(col => (
                                                                                <th key={col} className="p-1 text-[var(--text-muted)] font-normal truncate max-w-[80px]">
                                                                                    {col}
                                                                                </th>
                                                                            ))}
                                                                        </tr>
                                                                    </thead>
                                                                    <tbody>
                                                                        {Object.entries(tableStats.correlations).map(([row, cols]) => (
                                                                            <tr key={row}>
                                                                                <td className="p-1 text-[var(--text-muted)] truncate max-w-[80px]">{row}</td>
                                                                                {Object.entries(cols).map(([col, val]) => {
                                                                                    const absVal = Math.abs(val);
                                                                                    const color = row === col ? 'transparent' :
                                                                                        absVal > 0.7 ? 'var(--brand-primary)' :
                                                                                            absVal > 0.4 ? 'var(--brand-primary-light)' : 'var(--bg-tertiary)';
                                                                                    return (
                                                                                        <td
                                                                                            key={col}
                                                                                            className="p-1 text-center"
                                                                                            style={{ backgroundColor: color, opacity: row === col ? 1 : 0.3 + absVal * 0.7 }}
                                                                                        >
                                                                                            {row !== col && val.toFixed(2)}
                                                                                        </td>
                                                                                    );
                                                                                })}
                                                                            </tr>
                                                                        ))}
                                                                    </tbody>
                                                                </table>
                                                            </div>
                                                        </div>
                                                    )}
                                                </div>
                                            )}
                                        </div>
                                    );
                                })}
                            </div>
                        )
                    }

                    {/* Issues Tab */}
                    {
                        activeTab === 'issues' && (
                            <div className="space-y-3">
                                {report.quality_issues.length === 0 ? (
                                    <div className="text-center py-12">
                                        <CheckCircle className="w-16 h-16 mx-auto text-[var(--success)] mb-4" />
                                        <h3 className="text-lg font-medium text-[var(--text-primary)]">No Issues Found</h3>
                                        <p className="text-sm text-[var(--text-muted)]">Your data quality looks great!</p>
                                    </div>
                                ) : (
                                    report.quality_issues.map((issue, i) => (
                                        <div key={i} className="card p-4 flex items-start gap-3">
                                            {getIssueIcon(issue.type)}
                                            <div>
                                                <div className="text-sm text-[var(--text-primary)]">
                                                    {getIssueDescription(issue)}
                                                </div>
                                                <div className="text-xs text-[var(--text-muted)] mt-1">
                                                    Table: {issue.table}
                                                </div>
                                            </div>
                                        </div>
                                    ))
                                )}
                            </div>
                        )
                    }
                </div >
            </div >
        </div >
    );
}
