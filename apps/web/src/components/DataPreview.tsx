"use client";

import { useMemo } from 'react';
import { useSchemaStore, Column } from '@/store/schemaStore';

// Generate sample preview data based on column type
function generateSampleValue(column: Column, rowIndex: number): string {
    const { type, distributionParams } = column;
    const params = distributionParams || {};

    switch (type) {
        case 'int':
            if (params.distribution === 'sequence') {
                return String(rowIndex + 1);
            }
            const min = (params.min as number) || 1;
            const max = (params.max as number) || 100;
            return String(Math.floor(min + Math.random() * (max - min)));

        case 'float':
            const fMin = (params.min as number) || 0;
            const fMax = (params.max as number) || 1000;
            return (fMin + Math.random() * (fMax - fMin)).toFixed(2);

        case 'text':
            const dist = params.distribution as string;
            if (dist === 'fake.name') {
                const names = ['Emma Wilson', 'James Chen', 'Sofia Rodriguez', 'Liam Johnson', 'Olivia Brown'];
                return names[rowIndex % names.length];
            }
            if (dist === 'fake.email') {
                const emails = ['emma@example.com', 'james@test.io', 'sofia@demo.co', 'liam@mail.com', 'olivia@site.org'];
                return emails[rowIndex % emails.length];
            }
            if (dist === 'fake.company') {
                const companies = ['TechCorp', 'DataFlow Inc', 'CloudBase', 'AI Solutions', 'DevOps Ltd'];
                return companies[rowIndex % companies.length];
            }
            if (dist === 'uuid') {
                return `${Math.random().toString(36).substring(2, 10)}-${Math.random().toString(36).substring(2, 6)}`;
            }
            return `text_${rowIndex + 1}`;

        case 'date':
            const date = new Date();
            date.setDate(date.getDate() - Math.floor(Math.random() * 365));
            return date.toISOString().split('T')[0];

        case 'categorical':
            const choices = params.choices as string[] || ['A', 'B', 'C'];
            return choices[rowIndex % choices.length];

        case 'boolean':
            return Math.random() > 0.5 ? 'true' : 'false';

        case 'foreign_key':
            return String(Math.floor(Math.random() * 100) + 1);

        default:
            return '—';
    }
}

interface DataPreviewProps {
    tableId: string;
    isOpen: boolean;
    onClose: () => void;
}

export default function DataPreview({ tableId, isOpen, onClose }: DataPreviewProps) {
    const { tables } = useSchemaStore();
    const table = tables.find(t => t.id === tableId);

    const previewRows = useMemo(() => {
        if (!table) return [];
        return Array.from({ length: 5 }, (_, i) => {
            const row: Record<string, string> = {};
            table.columns.forEach(col => {
                row[col.name] = generateSampleValue(col, i);
            });
            return row;
        });
    }, [table]);

    if (!isOpen || !table) return null;

    return (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 animate-fade-in">
            <div className="card w-full max-w-4xl max-h-[80vh] m-4 flex flex-col">
                {/* Header */}
                <div className="flex items-center justify-between p-4 border-b border-zinc-800">
                    <div>
                        <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                            <span>👁️</span>
                            Data Preview: {table.name}
                        </h2>
                        <p className="text-xs text-zinc-500">
                            Sample of how generated data will look ({table.rowCount.toLocaleString()} rows will be generated)
                        </p>
                    </div>
                    <button
                        onClick={onClose}
                        className="text-zinc-500 hover:text-white transition-colors p-2"
                    >
                        ✕
                    </button>
                </div>

                {/* Table */}
                <div className="flex-1 overflow-auto p-4">
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="border-b border-zinc-800">
                                {table.columns.map(col => (
                                    <th
                                        key={col.id}
                                        className="text-left py-2 px-3 text-zinc-400 font-medium"
                                    >
                                        <div className="flex items-center gap-2">
                                            <span>{col.name}</span>
                                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-500 uppercase">
                                                {col.type}
                                            </span>
                                        </div>
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {previewRows.map((row, i) => (
                                <tr key={i} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                                    {table.columns.map(col => (
                                        <td key={col.id} className="py-2 px-3 text-zinc-300 font-mono text-xs">
                                            {row[col.name]}
                                        </td>
                                    ))}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                {/* Footer */}
                <div className="flex items-center justify-between p-4 border-t border-zinc-800 bg-zinc-900/50">
                    <p className="text-xs text-zinc-500">
                        Showing 5 sample rows • Actual data will be unique
                    </p>
                    <div className="flex gap-2">
                        <button onClick={onClose} className="btn btn-secondary text-xs">
                            Close
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}
