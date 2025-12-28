"use client";

import { useState, useEffect, useCallback } from 'react';
import { getJobStatus, downloadJobFiles, JobResponse, getCompletedJobs, deleteJob } from '@/lib/api';
import DataViewer from '@/components/DataViewer';
import QualityReport from '@/components/QualityReport';
import {
    Activity,
    CheckCircle,
    XCircle,
    Clock,
    Loader2,
    Download,
    BarChart3,
    FileStack,
    Rows3,
    Inbox,
    X,
    Table2,
    Eye,
    RefreshCw,
    Trash2,
    AlertTriangle
} from 'lucide-react';

interface Job {
    id: string;
    status: 'PENDING' | 'PROGRESS' | 'SUCCESS' | 'FAILURE';
    progress: number;
    schemaName: string;
    tables: number;
    rows: number;
    createdAt: string;
    files?: Record<string, string>;
    error?: string;
}

interface QualityReport {
    job_id: string;
    summary: {
        total_tables: number;
        total_rows: number;
        total_columns: number;
        quality_score: number;
    };
    tables: Record<string, {
        row_count: number;
        column_count: number;
        file_size_kb: number;
        columns: Record<string, {
            dtype: string;
            null_count: number;
            null_pct: number;
            unique_count: number;
            min?: number;
            max?: number;
            mean?: number;
        }>;
    }>;
}

const statusConfig = {
    PENDING: {
        icon: Clock,
        bg: 'bg-[var(--warning-muted)]',
        text: 'text-[var(--warning)]',
        label: 'Queued'
    },
    PROGRESS: {
        icon: Loader2,
        bg: 'bg-[var(--info-muted)]',
        text: 'text-[var(--info)]',
        label: 'Processing'
    },
    SUCCESS: {
        icon: CheckCircle,
        bg: 'bg-[var(--success-muted)]',
        text: 'text-[var(--success)]',
        label: 'Completed'
    },
    FAILURE: {
        icon: XCircle,
        bg: 'bg-[var(--error-muted)]',
        text: 'text-[var(--error)]',
        label: 'Failed'
    },
};

export default function JobsPage() {
    const [jobs, setJobs] = useState<Job[]>([]);
    const [filter, setFilter] = useState<'all' | 'running' | 'completed'>('all');
    const [isLoading, setIsLoading] = useState(true);
    const [isSyncing, setIsSyncing] = useState(false);
    const [selectedReport, setSelectedReport] = useState<QualityReport | null>(null);
    const [loadingReport, setLoadingReport] = useState<string | null>(null);
    const [viewingJobId, setViewingJobId] = useState<string | null>(null);
    const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
    const [isDeleting, setIsDeleting] = useState(false);

    // Sync with server completed jobs
    const syncServerJobs = useCallback(async () => {
        setIsSyncing(true);
        try {
            const serverJobs = await getCompletedJobs();
            setJobs(prev => {
                // Create a map of existing jobs by ID
                const existingJobsMap = new Map(prev.map(j => [j.id, j]));

                // Add/update server jobs
                for (const serverJob of serverJobs) {
                    if (!existingJobsMap.has(serverJob.id)) {
                        existingJobsMap.set(serverJob.id, {
                            id: serverJob.id,
                            status: 'SUCCESS' as const,
                            progress: 100,
                            schemaName: serverJob.schema_name,
                            tables: serverJob.tables,
                            rows: serverJob.rows,
                            createdAt: serverJob.created_at,
                        });
                    } else {
                        // Update existing job if completed on server
                        const existing = existingJobsMap.get(serverJob.id)!;
                        if (existing.status !== 'SUCCESS') {
                            existingJobsMap.set(serverJob.id, {
                                ...existing,
                                status: 'SUCCESS' as const,
                                progress: 100,
                                tables: serverJob.tables,
                                rows: serverJob.rows,
                            });
                        }
                    }
                }

                const merged = Array.from(existingJobsMap.values())
                    .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
                localStorage.setItem('misata_jobs', JSON.stringify(merged));
                return merged;
            });
        } catch (err) {
            console.error('Failed to sync server jobs:', err);
        } finally {
            setIsSyncing(false);
        }
    }, []);

    useEffect(() => {
        // Load from localStorage first
        const storedJobs = localStorage.getItem('misata_jobs');
        if (storedJobs) {
            try {
                setJobs(JSON.parse(storedJobs));
            } catch { }
        }
        setIsLoading(false);

        // Then sync with server
        syncServerJobs();
    }, [syncServerJobs]);

    useEffect(() => {
        const runningJobs = jobs.filter(j => j.status === 'PENDING' || j.status === 'PROGRESS');
        if (runningJobs.length === 0) return;

        const interval = setInterval(async () => {
            const updates = await Promise.all(
                runningJobs.map(async (job) => {
                    try {
                        const status = await getJobStatus(job.id);
                        return {
                            ...job,
                            status: status.status as Job['status'],
                            progress: status.progress || 0,
                            files: status.files,
                            error: status.error,
                        };
                    } catch {
                        return job;
                    }
                })
            );

            setJobs(prev => {
                const updated = prev.map(j => {
                    const update = updates.find(u => u.id === j.id);
                    return update || j;
                });
                localStorage.setItem('misata_jobs', JSON.stringify(updated));
                return updated;
            });
        }, 2000);

        return () => clearInterval(interval);
    }, [jobs]);

    const filteredJobs = jobs.filter((job) => {
        if (filter === 'all') return true;
        if (filter === 'running') return job.status === 'PROGRESS' || job.status === 'PENDING';
        return job.status === 'SUCCESS';
    });

    const handleDownload = useCallback(async (jobId: string) => {
        try {
            const blob = await downloadJobFiles(jobId);
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `misata_${jobId.slice(0, 8)}.zip`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (err) {
            alert(`Download failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
        }
    }, []);

    const handleViewReport = useCallback(async (jobId: string) => {
        setLoadingReport(jobId);
        try {
            const response = await fetch(`http://localhost:8000/jobs/${jobId}/quality-report`);
            if (!response.ok) throw new Error('Failed to fetch report');
            const report = await response.json();
            setSelectedReport(report);
        } catch (err) {
            alert(`Failed to load report: ${err instanceof Error ? err.message : 'Unknown error'}`);
        } finally {
            setLoadingReport(null);
        }
    }, []);

    const handleDelete = useCallback(async (jobId: string) => {
        setIsDeleting(true);
        try {
            await deleteJob(jobId);
            setJobs(prev => {
                const updated = prev.filter(j => j.id !== jobId);
                localStorage.setItem('misata_jobs', JSON.stringify(updated));
                return updated;
            });
            setConfirmDeleteId(null);
        } catch (err) {
            alert(`Delete failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
        } finally {
            setIsDeleting(false);
        }
    }, []);

    const formatDate = (dateStr: string) => {
        const date = new Date(dateStr);
        return date.toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        });
    };

    const totalRows = jobs.reduce((acc, j) => acc + (j.rows || 0), 0);
    const completedCount = jobs.filter(j => j.status === 'SUCCESS').length;
    const runningCount = jobs.filter(j => j.status === 'PROGRESS' || j.status === 'PENDING').length;

    return (
        <div className="p-8 max-w-5xl mx-auto animate-fade-in">
            {/* Header */}
            <div className="flex items-center justify-between mb-8">
                <div>
                    <div className="flex items-center gap-3 mb-2">
                        <div className="w-10 h-10 rounded-lg bg-[var(--accent-muted)] flex items-center justify-center">
                            <Activity className="w-5 h-5 text-[var(--brand-primary-light)]" />
                        </div>
                        <h1 className="text-heading text-[var(--text-primary)]">
                            Jobs
                        </h1>
                    </div>
                    <p className="text-body">
                        Monitor and manage data generation jobs.
                    </p>
                </div>
                <div className="flex gap-2">
                    <button
                        onClick={syncServerJobs}
                        disabled={isSyncing}
                        className="btn btn-ghost btn-sm"
                        title="Sync with server"
                    >
                        <RefreshCw className={`w-4 h-4 ${isSyncing ? 'animate-spin' : ''}`} />
                    </button>
                    {(['all', 'running', 'completed'] as const).map((f) => (
                        <button
                            key={f}
                            onClick={() => setFilter(f)}
                            className={`btn btn-sm capitalize ${filter === f ? 'btn-primary' : 'btn-ghost'
                                }`}
                        >
                            {f}
                        </button>
                    ))}
                </div>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-4 gap-4 mb-8">
                {[
                    { label: 'Total Jobs', value: jobs.length, icon: FileStack },
                    { label: 'Completed', value: completedCount, icon: CheckCircle },
                    { label: 'Running', value: runningCount, icon: Loader2 },
                    { label: 'Total Rows', value: totalRows.toLocaleString(), icon: Rows3 },
                ].map((stat) => {
                    const Icon = stat.icon;
                    return (
                        <div key={stat.label} className="card p-4">
                            <div className="flex items-center gap-3">
                                <Icon className="w-5 h-5 text-[var(--text-muted)]" />
                                <div>
                                    <p className="text-xl font-semibold text-[var(--text-primary)]">{stat.value}</p>
                                    <p className="text-xs text-[var(--text-muted)]">{stat.label}</p>
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* Jobs List */}
            {isLoading ? (
                <div className="space-y-4">
                    {[1, 2, 3].map((i) => (
                        <div key={i} className="card p-6 shimmer h-24" />
                    ))}
                </div>
            ) : filteredJobs.length === 0 ? (
                <div className="card p-16 text-center">
                    <Inbox className="w-12 h-12 text-[var(--text-muted)] mx-auto mb-4" />
                    <h3 className="text-title text-[var(--text-secondary)] mb-2">No jobs yet</h3>
                    <p className="text-sm text-[var(--text-muted)]">
                        Generate data from the Builder or Story Mode to see jobs here.
                    </p>
                </div>
            ) : (
                <div className="space-y-4">
                    {filteredJobs.map((job) => {
                        const config = statusConfig[job.status] || statusConfig.PENDING;
                        const StatusIcon = config.icon;

                        return (
                            <div key={job.id} className="card p-5 hover:border-[var(--border-default)] transition-all">
                                <div className="flex items-start justify-between">
                                    <div className="flex-1">
                                        <div className="flex items-center gap-3 mb-2">
                                            <h3 className="text-title text-[var(--text-primary)]">
                                                {job.schemaName || `Job ${job.id.slice(0, 8)}`}
                                            </h3>
                                            <span className={`badge ${config.bg} ${config.text}`}>
                                                <StatusIcon className={`w-3 h-3 ${job.status === 'PROGRESS' ? 'animate-spin' : ''}`} />
                                                {config.label}
                                            </span>
                                        </div>

                                        <div className="flex items-center gap-4 text-xs text-[var(--text-muted)]">
                                            <span>{job.tables || '?'} tables</span>
                                            <span>{(job.rows || 0).toLocaleString()} rows</span>
                                            <span>{formatDate(job.createdAt)}</span>
                                        </div>

                                        {(job.status === 'PROGRESS' || job.status === 'PENDING') && (
                                            <div className="mt-3">
                                                <div className="flex items-center justify-between text-xs text-[var(--text-muted)] mb-1">
                                                    <span>Progress</span>
                                                    <span>{job.progress}%</span>
                                                </div>
                                                <div className="w-full h-1.5 bg-[var(--bg-secondary)] rounded-full overflow-hidden">
                                                    <div
                                                        className="h-full bg-[var(--brand-primary)] transition-all"
                                                        style={{ width: `${job.progress}%` }}
                                                    />
                                                </div>
                                            </div>
                                        )}

                                        {job.error && (
                                            <div className="mt-3 p-3 bg-[var(--error-muted)] border border-[var(--error)]/30 rounded-lg text-xs text-[var(--error)]">
                                                {job.error}
                                            </div>
                                        )}
                                    </div>

                                    <div className="flex gap-2 ml-4">
                                        {job.status === 'SUCCESS' && (
                                            <>
                                                <button
                                                    onClick={() => setViewingJobId(job.id)}
                                                    className="btn btn-secondary btn-sm"
                                                >
                                                    <Eye className="w-3.5 h-3.5" />
                                                    View Data
                                                </button>
                                                <button
                                                    onClick={() => handleViewReport(job.id)}
                                                    disabled={loadingReport === job.id}
                                                    className="btn btn-secondary btn-sm"
                                                >
                                                    {loadingReport === job.id ? (
                                                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                                    ) : (
                                                        <BarChart3 className="w-3.5 h-3.5" />
                                                    )}
                                                    Report
                                                </button>
                                                <button
                                                    onClick={() => handleDownload(job.id)}
                                                    className="btn btn-primary btn-sm"
                                                >
                                                    <Download className="w-3.5 h-3.5" />
                                                    Download
                                                </button>
                                                <button
                                                    onClick={() => setConfirmDeleteId(job.id)}
                                                    className="btn btn-ghost btn-sm text-[var(--error)] hover:bg-[var(--error-muted)]"
                                                    title="Delete dataset"
                                                >
                                                    <Trash2 className="w-3.5 h-3.5" />
                                                </button>
                                            </>
                                        )}
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}

            {/* Quality Report Modal */}
            <QualityReport
                report={selectedReport as any}
                isOpen={!!selectedReport}
                onClose={() => setSelectedReport(null)}
            />

            {/* Delete Confirmation Modal */}
            {confirmDeleteId && (
                <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 animate-fade-in">
                    <div className="card card-elevated w-full max-w-md m-4 p-6">
                        <div className="flex items-center gap-3 mb-4">
                            <div className="w-12 h-12 rounded-full bg-[var(--error-muted)] flex items-center justify-center">
                                <AlertTriangle className="w-6 h-6 text-[var(--error)]" />
                            </div>
                            <div>
                                <h3 className="text-title text-[var(--text-primary)]">Delete Dataset</h3>
                                <p className="text-sm text-[var(--text-muted)]">This action cannot be undone</p>
                            </div>
                        </div>

                        <p className="text-sm text-[var(--text-secondary)] mb-6">
                            Are you sure you want to delete this dataset? All generated data files will be permanently removed.
                        </p>

                        <div className="flex gap-3 justify-end">
                            <button
                                onClick={() => setConfirmDeleteId(null)}
                                disabled={isDeleting}
                                className="btn btn-ghost"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={() => handleDelete(confirmDeleteId)}
                                disabled={isDeleting}
                                className="btn bg-[var(--error)] hover:bg-[var(--error)]/90 text-white"
                            >
                                {isDeleting ? (
                                    <>
                                        <Loader2 className="w-4 h-4 animate-spin" />
                                        Deleting...
                                    </>
                                ) : (
                                    <>
                                        <Trash2 className="w-4 h-4" />
                                        Delete
                                    </>
                                )}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Data Viewer Modal */}
            <DataViewer
                jobId={viewingJobId || ''}
                isOpen={!!viewingJobId}
                onClose={() => setViewingJobId(null)}
            />
        </div>
    );
}
