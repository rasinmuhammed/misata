"use client";

import { memo, useCallback, useState, useMemo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { useSchemaStore, Column, OutcomeConstraint, CurvePoint } from '@/store/schemaStore';
import ColumnEditor from './ColumnEditor';
import DataPreview from './DataPreview';
import CurveEditor from './CurveEditor';
import { validateTableName, validateRowCount, ValidationResult } from '@/lib/validation';
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
    Check,
    AlertCircle,
    AlertTriangle,
    TrendingUp
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
    const { tables, setSelectedTable, addColumn, updateTable, removeTable, getConstraintForColumn, addOrUpdateConstraint } = useSchemaStore();
    const [editingColumn, setEditingColumn] = useState<Column | null>(null);
    const [isEditingName, setIsEditingName] = useState(false);
    const [showPreview, setShowPreview] = useState(false);
    const [tableName, setTableName] = useState(data.label);
    const [rowCount, setRowCount] = useState(data.rowCount);
    const [curveEditorColumn, setCurveEditorColumn] = useState<Column | null>(null);

    // Inline validation for table name
    const tableNameValidation = useMemo((): ValidationResult => {
        if (!isEditingName) return { isValid: true };
        const otherTableNames = tables
            .filter(t => t.id !== data.tableId)
            .map(t => t.name);
        return validateTableName(tableName, otherTableNames);
    }, [tableName, isEditingName, tables, data.tableId]);

    // Inline validation for row count
    const rowCountValidation = useMemo((): ValidationResult => {
        if (!isEditingName) return { isValid: true };
        return validateRowCount(rowCount);
    }, [rowCount, isEditingName]);

    // Can save only if both validations pass
    const canSave = tableNameValidation.isValid && rowCountValidation.isValid;

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
        if (!canSave) return;
        updateTable(data.tableId, { name: tableName, rowCount });
        setIsEditingName(false);
    }, [data.tableId, tableName, rowCount, updateTable, canSave]);

    const handleCancelEdit = useCallback(() => {
        setTableName(data.label);
        setRowCount(data.rowCount);
        setIsEditingName(false);
    }, [data.label, data.rowCount]);

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
                        <div className="space-y-2" onClick={(e) => e.stopPropagation()}>
                            <div className="flex gap-2">
                                <div className="flex-1">
                                    <input
                                        type="text"
                                        value={tableName}
                                        onChange={(e) => setTableName(e.target.value)}
                                        className={`w-full px-2 py-1 text-sm bg-white/20 border rounded text-white placeholder-white/50 ${!tableNameValidation.isValid
                                            ? 'border-red-400 bg-red-400/20'
                                            : tableNameValidation.warning
                                                ? 'border-yellow-400 bg-yellow-400/10'
                                                : 'border-white/30'
                                            }`}
                                        placeholder="Table name"
                                        autoFocus
                                        onKeyDown={(e) => {
                                            if (e.key === 'Enter' && canSave) handleNameSave();
                                            if (e.key === 'Escape') handleCancelEdit();
                                        }}
                                    />
                                </div>
                                <div>
                                    <input
                                        type="number"
                                        value={rowCount}
                                        onChange={(e) => setRowCount(Number(e.target.value))}
                                        className={`w-20 px-2 py-1 text-sm bg-white/20 border rounded text-white ${!rowCountValidation.isValid
                                            ? 'border-red-400 bg-red-400/20'
                                            : rowCountValidation.warning
                                                ? 'border-yellow-400 bg-yellow-400/10'
                                                : 'border-white/30'
                                            }`}
                                        min={1}
                                    />
                                </div>
                                <button
                                    onClick={handleNameSave}
                                    disabled={!canSave}
                                    className={`px-2 py-1 rounded text-white transition-colors ${canSave
                                        ? 'bg-white/20 hover:bg-white/30'
                                        : 'bg-white/10 opacity-50 cursor-not-allowed'
                                        }`}
                                    title={canSave ? 'Save' : 'Fix validation errors'}
                                >
                                    <Check className="w-4 h-4" />
                                </button>
                                <button
                                    onClick={handleCancelEdit}
                                    className="px-2 py-1 bg-white/10 rounded text-white hover:bg-white/20 transition-colors"
                                    title="Cancel"
                                >
                                    <X className="w-4 h-4" />
                                </button>
                            </div>
                            {/* Validation messages */}
                            {(!tableNameValidation.isValid || tableNameValidation.warning ||
                                !rowCountValidation.isValid || rowCountValidation.warning) && (
                                    <div className="space-y-1">
                                        {!tableNameValidation.isValid && (
                                            <div className="flex items-center gap-1.5 text-red-200 text-xs">
                                                <AlertCircle className="w-3 h-3 flex-shrink-0" />
                                                <span>{tableNameValidation.error}</span>
                                            </div>
                                        )}
                                        {tableNameValidation.warning && (
                                            <div className="flex items-center gap-1.5 text-yellow-200 text-xs">
                                                <AlertTriangle className="w-3 h-3 flex-shrink-0" />
                                                <span>{tableNameValidation.warning}</span>
                                            </div>
                                        )}
                                        {!rowCountValidation.isValid && (
                                            <div className="flex items-center gap-1.5 text-red-200 text-xs">
                                                <AlertCircle className="w-3 h-3 flex-shrink-0" />
                                                <span>{rowCountValidation.error}</span>
                                            </div>
                                        )}
                                        {rowCountValidation.warning && (
                                            <div className="flex items-center gap-1.5 text-yellow-200 text-xs">
                                                <AlertTriangle className="w-3 h-3 flex-shrink-0" />
                                                <span>{rowCountValidation.warning}</span>
                                            </div>
                                        )}
                                    </div>
                                )}
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
                        const isNumeric = col.type === 'int' || col.type === 'float';
                        const hasConstraint = getConstraintForColumn(col.id);

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

                                {/* Constraint indicator for numeric columns */}
                                {isNumeric && (
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            setCurveEditorColumn(col);
                                        }}
                                        className={`p-1 rounded transition-colors ${hasConstraint ? 'bg-[#588157] text-white' : 'text-[#8B9185] hover:bg-[#E8E6E0] hover:text-[#3A5A40]'}`}
                                        title={hasConstraint ? 'Edit outcome constraint' : 'Add outcome constraint'}
                                    >
                                        <TrendingUp className="w-3 h-3" />
                                    </button>
                                )}

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
                    onOpenCurveEditor={() => {
                        setCurveEditorColumn(editingColumn);
                        setEditingColumn(null);
                    }}
                />
            )}

            {/* Data Preview Modal */}
            <DataPreview
                tableId={data.tableId}
                isOpen={showPreview}
                onClose={() => setShowPreview(false)}
            />

            {/* MOONSHOT: Curve Editor Modal */}
            {curveEditorColumn && (
                <CurveEditor
                    constraint={getConstraintForColumn(curveEditorColumn.id) || {
                        id: `constraint_${Date.now()}`,
                        tableId: data.tableId,
                        columnId: curveEditorColumn.id,
                        curvePoints: Array.from({ length: 12 }, (_, i) => ({
                            timestamp: new Date(new Date().getFullYear(), i, 1).toISOString(),
                            value: 100000,
                        })),
                        timeUnit: 'month',
                        avgTransactionValue: 50,
                    }}
                    tableName={data.label}
                    columnName={curveEditorColumn.name}
                    onSave={(updatedConstraint) => {
                        addOrUpdateConstraint(updatedConstraint);
                        setCurveEditorColumn(null);
                    }}
                    onClose={() => setCurveEditorColumn(null)}
                />
            )}
        </>
    );
}

export default memo(TableNode);
