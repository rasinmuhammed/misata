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
    Search
} from 'lucide-react';

interface DataViewerProps {
    jobId: string;
    isOpen: boolean;
    onClose: () => void;
}

export default function DataViewer({ jobId, isOpen, onClose }: DataViewerProps) {
    const [data, setData] = useState<JobDataResponse | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [activeTable, setActiveTable] = useState<string>('');
    const [page, setPage] = useState(0);
    const [searchTerm, setSearchTerm] = useState('');
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

    if (!isOpen) return null;

    const currentTable = data?.tables[activeTable];
    const tableNames = data ? Object.keys(data.tables) : [];

    // Filter rows based on search
    const filteredRows = currentTable?.rows.filter(row => {
        if (!searchTerm) return true;
        return Object.values(row).some(val =>
            String(val).toLowerCase().includes(searchTerm.toLowerCase())
        );
    }) || [];

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
                    <button
                        onClick={onClose}
                        className="w-8 h-8 rounded-lg flex items-center justify-center transition-colors"
                        style={{ color: '#6B7164' }}
                    >
                        <X className="w-5 h-5" />
                    </button>
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
                                            ({data.tables[name].total_rows} rows)
                                        </span>
                                    </button>
                                ))}
                            </div>
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
                        </div>

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
            </div>
        </div>
    );
}
