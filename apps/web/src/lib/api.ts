const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface JobResponse {
    job_id: string;
    status: string;
    progress?: number;
    message?: string;
    files?: Record<string, string>;
    error?: string;
}

export interface SchemaConfig {
    name: string;
    tables: { name: string; row_count: number }[];
    columns: Record<string, { name: string; type: string; distribution_params?: Record<string, unknown> }[]>;
    relationships?: { parent_table: string; child_table: string; parent_key: string; child_key: string }[];
}

export interface LLMSchemaResponse {
    schema: SchemaConfig;
    explanation: string;
}

// ============ Job Management ============

export async function submitJob(schemaConfig: SchemaConfig): Promise<JobResponse> {
    const response = await fetch(`${API_BASE_URL}/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ schema_config: schemaConfig }),
    });

    if (!response.ok) {
        throw new Error(`Failed to submit job: ${response.statusText}`);
    }

    return response.json();
}

export async function getJobStatus(jobId: string): Promise<JobResponse> {
    const response = await fetch(`${API_BASE_URL}/jobs/${jobId}`);

    if (!response.ok) {
        throw new Error(`Failed to get job status: ${response.statusText}`);
    }

    return response.json();
}

export async function pollJobUntilComplete(
    jobId: string,
    onProgress?: (progress: number, message: string) => void,
    maxAttempts: number = 60,
    intervalMs: number = 1000
): Promise<JobResponse> {
    for (let i = 0; i < maxAttempts; i++) {
        const status = await getJobStatus(jobId);

        if (onProgress) {
            onProgress(status.progress || 0, status.message || status.status);
        }

        if (status.status === 'SUCCESS') {
            return status;
        }

        if (status.status === 'FAILURE') {
            throw new Error(status.error || 'Job failed');
        }

        await new Promise(resolve => setTimeout(resolve, intervalMs));
    }

    throw new Error('Job timed out');
}

export async function downloadJobFiles(jobId: string): Promise<Blob> {
    const response = await fetch(`${API_BASE_URL}/jobs/${jobId}/download`);

    if (!response.ok) {
        throw new Error(`Failed to download: ${response.statusText}`);
    }

    return response.blob();
}

export async function deleteJob(jobId: string): Promise<{ status: string; job_id: string }> {
    const response = await fetch(`${API_BASE_URL}/jobs/${jobId}`, {
        method: 'DELETE',
    });

    if (!response.ok) {
        throw new Error(`Failed to delete job: ${response.statusText}`);
    }

    return response.json();
}

export interface TableData {
    columns: string[];
    rows: Record<string, unknown>[];
    total_rows: number;
    preview_rows: number;
}

export interface JobDataResponse {
    job_id: string;
    tables: Record<string, TableData>;
}

export async function getJobData(jobId: string, limit: number = 100): Promise<JobDataResponse> {
    const response = await fetch(`${API_BASE_URL}/jobs/${jobId}/data?limit=${limit}`);

    if (!response.ok) {
        throw new Error(`Failed to get job data: ${response.statusText}`);
    }

    return response.json();
}

export interface CompletedJobInfo {
    id: string;
    status: string;
    tables: number;
    rows: number;
    created_at: string;
    schema_name: string;
}

export async function getCompletedJobs(): Promise<CompletedJobInfo[]> {
    const response = await fetch(`${API_BASE_URL}/jobs/completed`);

    if (!response.ok) {
        throw new Error(`Failed to get completed jobs: ${response.statusText}`);
    }

    const data = await response.json();
    return data.jobs;
}

// ============ LLM Schema Generation ============

export async function generateSchemaFromStory(
    story: string,
    onStream?: (chunk: string) => void
): Promise<LLMSchemaResponse> {
    const response = await fetch(`${API_BASE_URL}/schema/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ story }),
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(error.detail || 'Failed to generate schema');
    }

    // Handle streaming response
    if (response.headers.get('content-type')?.includes('text/event-stream')) {
        const reader = response.body?.getReader();
        const decoder = new TextDecoder();
        let result = '';

        if (reader) {
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value);
                result += chunk;

                if (onStream) {
                    onStream(chunk);
                }
            }
        }

        return JSON.parse(result);
    }

    return response.json();
}

// ============ Health Check ============

export async function checkApiHealth(): Promise<boolean> {
    try {
        const response = await fetch(`${API_BASE_URL}/`, {
            method: 'GET',
            signal: AbortSignal.timeout(3000)
        });
        return response.ok;
    } catch {
        return false;
    }
}
