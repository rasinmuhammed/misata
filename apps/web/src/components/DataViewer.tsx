"use client";

import { useState, useEffect, useCallback } from 'react';
import { getJobData, TableData, JobDataResponse } from '@/lib/api';
import {
    X,
    Table2,
    Rows3,
    Loader2,
    ChevronLeft,
    ChevronRight,
    Download,
    Search,
    BarChart3,
    TrendingUp
} from 'lucide-react';

interface DataViewerProps {
    jobId: string;
    isOpen: boolean;
    onClose: () => void;
}

interface TimeSeriesData {
    data_points: { timestamp: string; value: number }[];
    time_column: string;
    value_column: string;
    aggregation: string;
    total_records: number;
}

// Simple Bar Chart Component for Time Series
function TimeSeriesChart({ data, title }: { data: TimeSeriesData | null; title: string }) {
    if (!data || !data.data_points || data.data_points.length === 0) {
        return (
            <div className="flex items-center justify-center h-64 text-sm" style={{ color: '#6B7164' }}>
                No time-series data available
            </div>
        );
    }

    const maxValue = Math.max(...data.data_points.map(p => p.value));
    const minValue = Math.min(...data.data_points.map(p => p.value));
    const range = maxValue - minValue || 1;

    return (
        <div className="p-4">
            <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-medium" style={{ color: '#3A5A40' }}>{title}</h3>
                <span className="text-xs" style={{ color: '#6B7164' }}>
                    {data.total_records.toLocaleString()} records aggregated by month
                </span>
            </div>

            {/* Chart */}
            <div className="relative h-64 flex items-end gap-1 border-b border-l" style={{ borderColor: 'rgba(58, 90, 64, 0.2)' }}>
                {/* Y-axis labels */}
                <div className="absolute left-0 top-0 bottom-0 w-16 flex flex-col justify-between text-xs -ml-16 pr-2" style={{ color: '#6B7164' }}>
                    <span>{maxValue.toLocaleString()}</span>
                    <span>{(maxValue / 2).toLocaleString()}</span>
                    <span>0</span>
                </div>

                {/* Bars */}
                {data.data_points.map((point, i) => {
                    const height = ((point.value - 0) / maxValue) * 100;
                    return (
                        <div
                            key={i}
                            className="flex-1 flex flex-col items-center justify-end group"
                        >
                            <div className="relative w-full flex justify-center">
                                {/* Tooltip */}
                                <div className="absolute -top-8 bg-[#3A5A40] text-white text-xs px-2 py-1 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap z-10">
                                    {point.value.toLocaleString()}
                                </div>
                                <div
                                    className="w-full max-w-8 rounded-t transition-all group-hover:opacity-80"
                                    style={{
                                        height: `${Math.max(height, 2)}%`,
                                        background: 'linear-gradient(to top, #588157, #7CB97C)',
                                    }}
                                />
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* X-axis labels */}
            <div className="flex gap-1 mt-2 overflow-x-auto">
                {data.data_points.map((point, i) => (
                    <div
                        key={i}
                        className="flex-1 text-center text-xs truncate min-w-8"
                        style={{ color: '#6B7164' }}
                        title={point.timestamp}
                    >
                        {point.timestamp.slice(0, 7)}
                    </div>
                ))}
            </div>

            {/* Legend */}
            <div className="flex items-center justify-center gap-6 mt-4 text-xs" style={{ color: '#6B7164' }}>
                <div className="flex items-center gap-2">
                    <TrendingUp className="w-4 h-4" style={{ color: '#588157' }} />
                    <span>{data.value_column} (sum by month)</span>
                </div>
            </div>
        </div>
    );
}

export default function DataViewer({ jobId, isOpen, onClose }: DataViewerProps) {
    const [data, setData] = useState<JobDataResponse | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [activeTable, setActiveTable] = useState<string>('');
    const [page, setPage] = useState(0);
    const [searchTerm, setSearchTerm] = useState('');
    const [viewMode, setViewMode] = useState<'table' | 'chart'>('table');
    const [chartData, setChartData] = useState<TimeSeriesData | null>(null);
    const [chartLoading, setChartLoading] = useState(false);
    const [chartError, setChartError] = useState<string | null>(null);
    const rowsPerPage = 25;

    useEffect(() => {
        if (isOpen && jobId && !data) {
            loadData();
        }
    }, [isOpen, jobId]);

    const loadData = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const result = await getJobData(jobId, 500); // Load up to 500 rows
            setData(result);
            const tableNames = Object.keys(result.tables);
            if (tableNames.length > 0) {
                setActiveTable(tableNames[0]);
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load data');
        } finally {
            setLoading(false);
        }
    }, [jobId]);

    const loadChartData = useCallback(async (tableName: string) => {
        setChartLoading(true);
        setChartError(null);
        try {
            // Get table columns to auto-detect time and numeric columns
            const tableData = data?.tables[tableName];
            const columns = tableData?.columns || [];

            // Auto-detect time column (prefer event_time, then date, then any with time/date in name)
            const timeColCandidates = ['event_time', 'date', 'created_at', 'timestamp', 'time'];
            let timeColumn = timeColCandidates.find(c => columns.includes(c));
            if (!timeColumn) {
                timeColumn = columns.find(c =>
                    c.toLowerCase().includes('time') ||
                    c.toLowerCase().includes('date')
                );
            }

            // Auto-detect numeric column (prefer amount, then value, then any numeric-sounding)
            const numColCandidates = ['amount', 'value', 'price', 'total', 'quantity', 'count'];
            let valueColumn = numColCandidates.find(c => columns.includes(c));
            if (!valueColumn) {
                valueColumn = columns.find(c =>
                    c.toLowerCase().includes('amount') ||
                    c.toLowerCase().includes('value') ||
                    c.toLowerCase().includes('price')
                );
            }

            if (!timeColumn) {
                throw new Error(`No time column found. Available columns: ${columns.join(', ')}`);
            }
            if (!valueColumn) {
                throw new Error(`No numeric column found for aggregation. Available columns: ${columns.join(', ')}`);
            }

            // Try to get time-series data with auto-detected columns
            const response = await fetch(
                `http://localhost:8000/jobs/${jobId}/timeseries/${tableName}?time_column=${timeColumn}&value_column=${valueColumn}&aggregation=sum`
            );

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || 'Failed to load chart data');
            }

            const tsData = await response.json();
            setChartData(tsData);
        } catch (err) {
            setChartError(err instanceof Error ? err.message : 'Failed to load chart data');
            setChartData(null);
        } finally {
            setChartLoading(false);
        }
    }, [jobId, data]);

    // Load chart data when switching to chart view or changing table
    useEffect(() => {
        if (viewMode === 'chart' && activeTable && jobId) {
            loadChartData(activeTable);
        }
    }, [viewMode, activeTable, jobId, loadChartData]);

    if (!isOpen) return null;

    const currentTable = data?.tables[activeTable];
    const tableNames = data ? Object.keys(data.tables) : [];

    // Safety check: Ensure rows is an array (backend might return just row count)
    const rawRows = currentTable?.rows;
    const safeRows = Array.isArray(rawRows) ? rawRows : [];

    // Filter rows based on search
    const filteredRows = safeRows.filter(row => {
        if (!searchTerm) return true;
        return Object.values(row).some(val =>
            String(val).toLowerCase().includes(searchTerm.toLowerCase())
        );
    });

    const totalPages = Math.ceil(filteredRows.length / rowsPerPage);
    const paginatedRows = filteredRows.slice(page * rowsPerPage, (page + 1) * rowsPerPage);

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.5)' }}>
            <div
                className="w-full max-w-6xl max-h-[85vh] flex flex-col rounded-xl overflow-hidden shadow-2xl"
                style={{ background: '#FEFEFE' }}
            >
                {/* Header */}
                <div
                    className="flex items-center justify-between px-6 py-4 border-b"
                    style={{ borderColor: 'rgba(58, 90, 64, 0.15)', background: '#F5F3EF' }}
                >
                    <div className="flex items-center gap-3">
                        <div
                            className="w-10 h-10 rounded-xl flex items-center justify-center"
                            style={{ background: 'rgba(88, 129, 87, 0.15)' }}
                        >
                            <Table2 className="w-5 h-5" style={{ color: '#3A5A40' }} />
                        </div>
                        <div>
                            <h2 className="text-lg font-semibold" style={{ color: '#3A5A40' }}>
                                Data Viewer
                            </h2>
                            <p className="text-xs" style={{ color: '#6B7164' }}>
                                Job: {jobId.slice(0, 8)}...
                            </p>
                        </div>
                    </div>

                    {/* View Mode Toggle */}
                    <div className="flex items-center gap-2">
                        <div className="flex rounded-lg overflow-hidden border" style={{ borderColor: 'rgba(58, 90, 64, 0.2)' }}>
                            <button
                                onClick={() => setViewMode('table')}
                                className="px-3 py-1.5 text-sm flex items-center gap-1.5 transition-colors"
                                style={{
                                    background: viewMode === 'table' ? '#588157' : 'transparent',
                                    color: viewMode === 'table' ? 'white' : '#4A6B4A'
                                }}
                            >
                                <Table2 className="w-4 h-4" />
                                Table
                            </button>
                            <button
                                onClick={() => setViewMode('chart')}
                                className="px-3 py-1.5 text-sm flex items-center gap-1.5 transition-colors"
                                style={{
                                    background: viewMode === 'chart' ? '#588157' : 'transparent',
                                    color: viewMode === 'chart' ? 'white' : '#4A6B4A'
                                }}
                            >
                                <BarChart3 className="w-4 h-4" />
                                Chart
                            </button>
                        </div>
                        <button
                            onClick={onClose}
                            className="w-8 h-8 rounded-lg flex items-center justify-center transition-colors ml-2"
                            style={{ color: '#6B7164' }}
                        >
                            <X className="w-5 h-5" />
                        </button>
                    </div>
                </div>

                {/* Loading State */}
                {loading && (
                    <div className="flex-1 flex items-center justify-center py-20">
                        <Loader2 className="w-8 h-8 animate-spin" style={{ color: '#588157' }} />
                    </div>
                )}

                {/* Error State */}
                {error && (
                    <div className="flex-1 flex items-center justify-center py-20">
                        <div className="text-center">
                            <p className="text-sm mb-2" style={{ color: '#9B4D4D' }}>{error}</p>
                            <button
                                onClick={loadData}
                                className="text-sm px-4 py-2 rounded-lg"
                                style={{ background: '#588157', color: 'white' }}
                            >
                                Retry
                            </button>
                        </div>
                    </div>
                )}

                {/* Data View */}
                {data && !loading && (
                    <>
                        {/* Table Tabs & Search */}
                        <div
                            className="flex items-center justify-between px-6 py-3 border-b"
                            style={{ borderColor: 'rgba(58, 90, 64, 0.1)' }}
                        >
                            <div className="flex gap-2">
                                {tableNames.map(name => (
                                    <button
                                        key={name}
                                        onClick={() => { setActiveTable(name); setPage(0); }}
                                        className="px-4 py-2 text-sm font-medium rounded-lg transition-colors"
                                        style={{
                                            background: activeTable === name ? '#588157' : 'transparent',
                                            color: activeTable === name ? 'white' : '#4A6B4A'
                                        }}
                                    >
                                        {name}
                                        <span
                                            className="ml-2 text-xs opacity-70"
                                        >
                                            ({(data.tables[name] as any).total_rows || (data.tables[name] as any).rows} rows)
                                        </span>
                                    </button>
                                ))}
                            </div>
                            {viewMode === 'table' && (
                                <div className="relative">
                                    <Search
                                        className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4"
                                        style={{ color: '#6B7164' }}
                                    />
                                    <input
                                        type="text"
                                        placeholder="Search..."
                                        value={searchTerm}
                                        onChange={(e) => { setSearchTerm(e.target.value); setPage(0); }}
                                        className="pl-9 pr-4 py-2 text-sm rounded-lg border"
                                        style={{
                                            borderColor: 'rgba(58, 90, 64, 0.2)',
                                            background: 'white'
                                        }}
                                    />
                                </div>
                            )}
                        </div>

                        {/* Table View */}
                        {viewMode === 'table' && (
                            <>
                                {/* No Preview Data Warning */}
                                {currentTable && (!Array.isArray((currentTable as any).rows) || (currentTable as any).rows.length === 0) && (
                                    <div className="mx-6 mt-4 p-4 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-sm flex items-center gap-2">
                                        <Download className="w-4 h-4" />
                                        <span>
                                            Preview not available for this dataset. Please download the full files to view the data.
                                        </span>
                                    </div>
                                )}

                                {/* Table */}
                                <div className="flex-1 overflow-auto">
                                    {currentTable && (
                                        <table className="w-full text-sm">
                                            <thead className="sticky top-0" style={{ background: '#F5F3EF' }}>
                                                <tr>
                                                    {currentTable.columns.map(col => (
                                                        <th
                                                            key={col}
                                                            className="text-left px-4 py-3 font-medium border-b"
                                                            style={{
                                                                color: '#3A5A40',
                                                                borderColor: 'rgba(58, 90, 64, 0.15)'
                                                            }}
                                                        >
                                                            {col}
                                                        </th>
                                                    ))}
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {paginatedRows.map((row, idx) => (
                                                    <tr
                                                        key={idx}
                                                        className="border-b hover:bg-[#F5F3EF] transition-colors"
                                                        style={{ borderColor: 'rgba(58, 90, 64, 0.08)' }}
                                                    >
                                                        {currentTable.columns.map(col => (
                                                            <td
                                                                key={col}
                                                                className="px-4 py-2.5"
                                                                style={{ color: '#4A6B4A' }}
                                                            >
                                                                {String(row[col] ?? '')}
                                                            </td>
                                                        ))}
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    )}
                                </div>

                                {/* Pagination */}
                                <div
                                    className="flex items-center justify-between px-6 py-3 border-t"
                                    style={{ borderColor: 'rgba(58, 90, 64, 0.15)', background: '#F5F3EF' }}
                                >
                                    <div className="flex items-center gap-2 text-sm" style={{ color: '#6B7164' }}>
                                        <Rows3 className="w-4 h-4" />
                                        Showing {page * rowsPerPage + 1}-{Math.min((page + 1) * rowsPerPage, filteredRows.length)} of {filteredRows.length}
                                        {currentTable && filteredRows.length < currentTable.total_rows && (
                                            <span className="text-xs opacity-70">
                                                (previewing {currentTable.preview_rows} of {currentTable.total_rows} total)
                                            </span>
                                        )}
                                    </div>
                                    <div className="flex gap-2">
                                        <button
                                            onClick={() => setPage(p => Math.max(0, p - 1))}
                                            disabled={page === 0}
                                            className="px-3 py-1.5 rounded-lg text-sm disabled:opacity-50"
                                            style={{ background: 'rgba(88, 129, 87, 0.1)', color: '#3A5A40' }}
                                        >
                                            <ChevronLeft className="w-4 h-4" />
                                        </button>
                                        <span className="px-3 py-1.5 text-sm" style={{ color: '#4A6B4A' }}>
                                            Page {page + 1} of {totalPages}
                                        </span>
                                        <button
                                            onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                                            disabled={page >= totalPages - 1}
                                            className="px-3 py-1.5 rounded-lg text-sm disabled:opacity-50"
                                            style={{ background: 'rgba(88, 129, 87, 0.1)', color: '#3A5A40' }}
                                        >
                                            <ChevronRight className="w-4 h-4" />
                                        </button>
                                    </div>
                                </div>
                            </>
                        )}

                        {/* Chart View */}
                        {viewMode === 'chart' && (
                            <div className="flex-1 overflow-auto p-6">
                                {chartLoading ? (
                                    <div className="flex items-center justify-center h-64">
                                        <Loader2 className="w-8 h-8 animate-spin" style={{ color: '#588157' }} />
                                    </div>
                                ) : chartError ? (
                                    <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 text-sm text-amber-800">
                                        <p className="font-medium mb-1">Chart not available</p>
                                        <p>{chartError}</p>
                                        <p className="mt-2 text-xs">
                                            Tip: Charts work best with tables that have a time column (event_time, created_at) and a numeric column (amount, value).
                                        </p>

                                        {/* Computed Revenue Fallback */}
                                        <div className="mt-4 p-3 bg-white rounded-lg border border-amber-100">
                                            <p className="font-medium text-sm mb-2" style={{ color: '#3A5A40' }}>💡 Try Computed Revenue</p>
                                            <p className="text-xs mb-2" style={{ color: '#6B7164' }}>
                                                For tables without an amount column, we can compute revenue by joining subscriptions with plan prices.
                                            </p>
                                            <button
                                                onClick={async () => {
                                                    setChartLoading(true);
                                                    setChartError(null);
                                                    try {
                                                        const response = await fetch(
                                                            `http://localhost:8000/jobs/${jobId}/computed/revenue`
                                                        );
                                                        if (!response.ok) {
                                                            const errorData = await response.json().catch(() => ({}));
                                                            throw new Error(errorData.detail || 'Failed to compute revenue');
                                                        }
                                                        const revenueData = await response.json();
                                                        setChartData({
                                                            data_points: revenueData.data_points,
                                                            time_column: 'month',
                                                            value_column: 'revenue',
                                                            aggregation: 'sum',
                                                            total_records: revenueData.total_records
                                                        });
                                                    } catch (err) {
                                                        setChartError(err instanceof Error ? err.message : 'Failed to compute revenue');
                                                    } finally {
                                                        setChartLoading(false);
                                                    }
                                                }}
                                                className="px-4 py-2 text-sm font-medium rounded-lg transition-colors"
                                                style={{ background: '#588157', color: 'white' }}
                                            >
                                                Calculate Revenue
                                            </button>
                                        </div>
                                    </div>
                                ) : (
                                    <div className="bg-white rounded-lg border" style={{ borderColor: 'rgba(58, 90, 64, 0.15)' }}>
                                        <TimeSeriesChart
                                            data={chartData}
                                            title={`${activeTable}: Amount by Month`}
                                        />
                                    </div>
                                )}

                                <div className="mt-4 p-4 bg-[#F5F3EF] rounded-lg text-sm" style={{ color: '#4A6B4A' }}>
                                    <p className="font-medium mb-2">📊 Constraint Verification</p>
                                    <p>
                                        This chart shows your generated data aggregated by month. Compare this with the outcome curve
                                        you defined in the Builder to verify the constraint was applied correctly.
                                    </p>
                                </div>
                            </div>
                        )}
                    </>
                )}
            </div>
        </div>
    );
}
