"use client";

import { memo, useCallback, useState } from 'react';
import { Handle, Position } from '@xyflow/react';
import { useSchemaStore, Column } from '@/store/schemaStore';
import ColumnEditor from './ColumnEditor';
import DataPreview from './DataPreview';
import {
    Hash,
    Type,
    Calendar,
    List,
    ToggleLeft,
    Link2,
    Plus,
    Eye,
    X,
    Check
} from 'lucide-react';

interface TableNodeData extends Record<string, unknown> {
    label: string;
    rowCount: number;
    columns: Column[];
    tableId: string;
}

// Refined type colors with botanical tones
const typeConfig: Record<string, { color: string; icon: typeof Hash }> = {
    int: { color: 'bg-[#5B8A8A]', icon: Hash },           // Teal
    float: { color: 'bg-[#7A9A7A]', icon: Hash },         // Sage
    text: { color: 'bg-[#588157]', icon: Type },          // Fern
    date: { color: 'bg-[#D4A574]', icon: Calendar },      // Terracotta
    time: { color: 'bg-[#C4956A]', icon: Calendar },      // Lighter terracotta
    datetime: { color: 'bg-[#B4856A]', icon: Calendar },  // Warm terracotta
    categorical: { color: 'bg-[#A3B18A]', icon: List },   // Dry sage
    boolean: { color: 'bg-[#8B7355]', icon: ToggleLeft }, // Brown
    foreign_key: { color: 'bg-[#3A5A40]', icon: Link2 },  // Hunter
};

interface TableNodeProps {
    id: string;
    data: TableNodeData;
    selected?: boolean;
}

function TableNode({ id, data, selected }: TableNodeProps) {
    const { setSelectedTable, addColumn, updateTable, removeTable } = useSchemaStore();
    const [editingColumn, setEditingColumn] = useState<Column | null>(null);
    const [isEditingName, setIsEditingName] = useState(false);
    const [showPreview, setShowPreview] = useState(false);
    const [tableName, setTableName] = useState(data.label);
    const [rowCount, setRowCount] = useState(data.rowCount);

    const handleClick = useCallback(() => {
        setSelectedTable(data.tableId);
    }, [data.tableId, setSelectedTable]);

    const handleAddColumn = useCallback((e: React.MouseEvent) => {
        e.stopPropagation();
        const newColumn: Column = {
            id: `col_${Date.now()}`,
            name: `column_${data.columns.length + 1}`,
            type: 'text',
        };
        addColumn(data.tableId, newColumn);
    }, [data.tableId, data.columns.length, addColumn]);

    const handleColumnClick = useCallback((e: React.MouseEvent, column: Column) => {
        e.stopPropagation();
        setEditingColumn(column);
    }, []);

    const handleNameSave = useCallback(() => {
        updateTable(data.tableId, { name: tableName, rowCount });
        setIsEditingName(false);
    }, [data.tableId, tableName, rowCount, updateTable]);

    const handleDelete = useCallback((e: React.MouseEvent) => {
        e.stopPropagation();
        if (confirm(`Delete table "${data.label}"?`)) {
            removeTable(data.tableId);
        }
    }, [data.tableId, data.label, removeTable]);

    return (
        <>
            <div
                onClick={handleClick}
                className={`
                    min-w-[280px] rounded-xl overflow-hidden
                    ${selected ? 'ring-2 ring-[#588157] ring-offset-2 ring-offset-[#DAD7CD]' : ''}
                    bg-[#FEFEFE] border border-[#C9C5BA]
                    transition-all duration-200 hover:border-[#588157]/50 
                    shadow-md hover:shadow-lg
                `}
            >
                {/* Header */}
                <div
                    className="px-4 py-3 cursor-pointer relative group"
                    style={{ background: 'linear-gradient(135deg, #3A5A40 0%, #588157 100%)' }}
                    onDoubleClick={() => setIsEditingName(true)}
                >
                    {/* Delete button */}
                    <button
                        onClick={handleDelete}
                        className="absolute top-2 right-2 w-6 h-6 rounded-full bg-white/10 text-white/70 hover:bg-red-500/80 hover:text-white opacity-0 group-hover:opacity-100 transition-all flex items-center justify-center"
                    >
                        <X className="w-3 h-3" />
                    </button>

                    {isEditingName ? (
                        <div className="flex gap-2" onClick={(e) => e.stopPropagation()}>
                            <input
                                type="text"
                                value={tableName}
                                onChange={(e) => setTableName(e.target.value)}
                                className="flex-1 px-2 py-1 text-sm bg-white/20 border border-white/30 rounded text-white placeholder-white/50"
                                autoFocus
                                onKeyDown={(e) => e.key === 'Enter' && handleNameSave()}
                            />
                            <input
                                type="number"
                                value={rowCount}
                                onChange={(e) => setRowCount(Number(e.target.value))}
                                className="w-20 px-2 py-1 text-sm bg-white/20 border border-white/30 rounded text-white"
                                min={1}
                            />
                            <button
                                onClick={handleNameSave}
                                className="px-2 py-1 bg-white/20 rounded text-white hover:bg-white/30"
                            >
                                <Check className="w-4 h-4" />
                            </button>
                        </div>
                    ) : (
                        <div className="flex items-center justify-between pr-8">
                            <span className="text-white font-semibold text-sm">{data.label}</span>
                            <span className="text-white/80 text-xs bg-white/15 px-2 py-0.5 rounded-full">
                                {data.rowCount.toLocaleString()} rows
                            </span>
                        </div>
                    )}
                </div>

                {/* Columns */}
                <div className="p-2 space-y-1 bg-[#FEFEFE]">
                    {data.columns.map((col: Column) => {
                        const config = typeConfig[col.type] || { color: 'bg-gray-400', icon: Hash };
                        const Icon = config.icon;

                        return (
                            <div
                                key={col.id}
                                onClick={(e) => handleColumnClick(e, col)}
                                className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[#F5F3EF] hover:bg-[#E8E6E0] transition-colors cursor-pointer group relative"
                            >
                                {/* Source handle */}
                                <Handle
                                    type="source"
                                    position={Position.Right}
                                    id={`${col.id}-source`}
                                    className="!w-2.5 !h-2.5 !bg-[#588157] !border-2 !border-white opacity-0 group-hover:opacity-100 transition-opacity"
                                    style={{ top: 'auto', right: -5 }}
                                />
                                {/* Target handle */}
                                <Handle
                                    type="target"
                                    position={Position.Left}
                                    id={`${col.id}-target`}
                                    className="!w-2.5 !h-2.5 !bg-[#3A5A40] !border-2 !border-white opacity-0 group-hover:opacity-100 transition-opacity"
                                    style={{ top: 'auto', left: -5 }}
                                />

                                <span className={`w-5 h-5 rounded flex items-center justify-center ${config.color}`}>
                                    <Icon className="w-3 h-3 text-white" strokeWidth={2.5} />
                                </span>
                                <span className="text-[#3A5A40] text-xs flex-1 truncate font-medium">{col.name}</span>
                                <span className="text-[#8B9185] text-[10px] uppercase tracking-wider font-medium">{col.type}</span>
                            </div>
                        );
                    })}

                    {/* Action Buttons */}
                    <div className="flex gap-2 mt-2 pt-2 border-t border-[#E8E6E0]">
                        <button
                            onClick={handleAddColumn}
                            className="flex-1 py-2 text-xs text-[#588157] hover:text-white hover:bg-[#588157] rounded-lg transition-colors flex items-center justify-center gap-1.5 font-medium"
                        >
                            <Plus className="w-3.5 h-3.5" />
                            Add Column
                        </button>
                        <button
                            onClick={(e) => { e.stopPropagation(); setShowPreview(true); }}
                            className="py-2 px-3 text-xs text-[#6B7164] hover:text-[#3A5A40] hover:bg-[#E8E6E0] rounded-lg transition-colors"
                            title="Preview sample data"
                        >
                            <Eye className="w-3.5 h-3.5" />
                        </button>
                    </div>
                </div>
            </div>

            {/* Column Editor Modal */}
            {editingColumn && (
                <ColumnEditor
                    tableId={data.tableId}
                    column={editingColumn}
                    onClose={() => setEditingColumn(null)}
                />
            )}

            {/* Data Preview Modal */}
            <DataPreview
                tableId={data.tableId}
                isOpen={showPreview}
                onClose={() => setShowPreview(false)}
            />
        </>
    );
}

export default memo(TableNode);
