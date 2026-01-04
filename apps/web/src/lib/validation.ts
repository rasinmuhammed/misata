/**
 * Schema Validation Utilities
 * 
 * Provides inline validation for table names, column names, and other schema properties.
 */

export interface ValidationResult {
    isValid: boolean;
    error?: string;
    warning?: string;
}

// SQL reserved keywords that should not be used as identifiers
const SQL_RESERVED_KEYWORDS = new Set([
    'select', 'from', 'where', 'insert', 'update', 'delete', 'create', 'drop',
    'table', 'column', 'index', 'view', 'database', 'schema', 'alter', 'add',
    'constraint', 'primary', 'foreign', 'key', 'references', 'null', 'not',
    'and', 'or', 'in', 'between', 'like', 'is', 'as', 'on', 'join', 'left',
    'right', 'inner', 'outer', 'full', 'cross', 'natural', 'using', 'order',
    'by', 'group', 'having', 'limit', 'offset', 'union', 'intersect', 'except',
    'all', 'distinct', 'true', 'false', 'case', 'when', 'then', 'else', 'end',
    'if', 'exists', 'unique', 'check', 'default', 'auto_increment', 'serial',
    'integer', 'int', 'float', 'double', 'decimal', 'numeric', 'varchar', 'char',
    'text', 'blob', 'date', 'time', 'datetime', 'timestamp', 'boolean', 'bool',
]);

/**
 * Validates a table name for SQL compatibility
 */
export function validateTableName(name: string, existingNames: string[] = []): ValidationResult {
    // Empty check
    if (!name || name.trim().length === 0) {
        return { isValid: false, error: 'Table name is required' };
    }

    const trimmedName = name.trim();

    // Length check
    if (trimmedName.length > 64) {
        return { isValid: false, error: 'Table name must be 64 characters or less' };
    }

    if (trimmedName.length < 2) {
        return { isValid: false, error: 'Table name must be at least 2 characters' };
    }

    // Must start with a letter or underscore
    if (!/^[a-zA-Z_]/.test(trimmedName)) {
        return { isValid: false, error: 'Table name must start with a letter or underscore' };
    }

    // Only alphanumeric and underscores allowed
    if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(trimmedName)) {
        return { isValid: false, error: 'Table name can only contain letters, numbers, and underscores' };
    }

    // Check for reserved keywords
    if (SQL_RESERVED_KEYWORDS.has(trimmedName.toLowerCase())) {
        return { isValid: true, warning: `"${trimmedName}" is a SQL reserved keyword - strict SQL databases may require quoting` };
    }

    // Check for duplicates (case-insensitive)
    const lowerName = trimmedName.toLowerCase();
    const isDuplicate = existingNames.some(
        existing => existing.toLowerCase() === lowerName
    );
    if (isDuplicate) {
        return { isValid: false, error: 'A table with this name already exists' };
    }

    // Warn about all-uppercase names
    if (trimmedName === trimmedName.toUpperCase() && trimmedName.length > 3) {
        return { isValid: true, warning: 'Consider using snake_case for readability' };
    }

    return { isValid: true };
}

/**
 * Validates a column name for SQL compatibility
 */
export function validateColumnName(
    name: string,
    existingNames: string[] = [],
    tableName?: string
): ValidationResult {
    // Empty check
    if (!name || name.trim().length === 0) {
        return { isValid: false, error: 'Column name is required' };
    }

    const trimmedName = name.trim();

    // Length check
    if (trimmedName.length > 64) {
        return { isValid: false, error: 'Column name must be 64 characters or less' };
    }

    if (trimmedName.length < 1) {
        return { isValid: false, error: 'Column name is required' };
    }

    // Must start with a letter or underscore
    if (!/^[a-zA-Z_]/.test(trimmedName)) {
        return { isValid: false, error: 'Column name must start with a letter or underscore' };
    }

    // Only alphanumeric and underscores allowed
    if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(trimmedName)) {
        return { isValid: false, error: 'Column name can only contain letters, numbers, and underscores' };
    }

    // Check for reserved keywords
    if (SQL_RESERVED_KEYWORDS.has(trimmedName.toLowerCase())) {
        return { isValid: true, warning: `"${trimmedName}" is a SQL reserved keyword - strict SQL databases may require quoting` };
    }

    // Check for duplicates within the same table
    const lowerName = trimmedName.toLowerCase();
    const isDuplicate = existingNames.some(
        existing => existing.toLowerCase() === lowerName
    );
    if (isDuplicate) {
        return { isValid: false, error: 'A column with this name already exists in this table' };
    }

    // Warn about column name same as table name
    if (tableName && trimmedName.toLowerCase() === tableName.toLowerCase()) {
        return { isValid: true, warning: 'Column name matches table name - consider a more descriptive name' };
    }

    return { isValid: true };
}

/**
 * Validates row count
 */
export function validateRowCount(count: number | string): ValidationResult {
    const numCount = typeof count === 'string' ? parseInt(count, 10) : count;

    if (isNaN(numCount)) {
        return { isValid: false, error: 'Row count must be a number' };
    }

    if (!Number.isInteger(numCount)) {
        return { isValid: false, error: 'Row count must be a whole number' };
    }

    if (numCount < 1) {
        return { isValid: false, error: 'Row count must be at least 1' };
    }

    if (numCount > 10_000_000) {
        return { isValid: false, error: 'Row count cannot exceed 10 million' };
    }

    // Warning for very large datasets
    if (numCount > 1_000_000) {
        return { isValid: true, warning: 'Large datasets may take longer to generate' };
    }

    if (numCount > 100_000) {
        return { isValid: true, warning: 'Consider using smaller batches for faster feedback' };
    }

    return { isValid: true };
}

/**
 * Validates distribution parameters based on type
 */
export function validateDistributionParams(
    type: string,
    distribution: string,
    params: Record<string, unknown>
): ValidationResult {
    switch (type) {
        case 'int':
        case 'float': {
            const min = params.min as number;
            const max = params.max as number;

            if (min !== undefined && max !== undefined && min > max) {
                return { isValid: false, error: 'Minimum value cannot be greater than maximum' };
            }

            if (distribution === 'normal') {
                const std = params.std as number;
                if (std !== undefined && std < 0) {
                    return { isValid: false, error: 'Standard deviation must be positive' };
                }
            }
            break;
        }

        case 'categorical': {
            const values = params.values as string[];
            if (!values || values.length === 0) {
                return { isValid: false, error: 'At least one category value is required' };
            }

            const weights = params.weights as number[];
            if (weights && weights.length !== values.length) {
                return { isValid: false, error: 'Number of weights must match number of values' };
            }

            if (weights && weights.some(w => w < 0)) {
                return { isValid: false, error: 'Weights cannot be negative' };
            }
            break;
        }

        case 'text': {
            if (distribution === 'pattern') {
                const pattern = params.pattern as string;
                if (!pattern || pattern.trim().length === 0) {
                    return { isValid: false, error: 'Pattern is required for pattern distribution' };
                }
            }
            break;
        }

        case 'date':
        case 'datetime': {
            const start = params.start as string;
            const end = params.end as string;

            if (start && end) {
                const startDate = new Date(start);
                const endDate = new Date(end);

                if (startDate > endDate) {
                    return { isValid: false, error: 'Start date cannot be after end date' };
                }
            }
            break;
        }
    }

    return { isValid: true };
}

/**
 * Validates the entire schema before generation
 */
export interface SchemaValidationResult {
    isValid: boolean;
    errors: Array<{ path: string; message: string }>;
    warnings: Array<{ path: string; message: string }>;
}

export function validateSchema(schema: {
    tables: Array<{
        id: string;
        name: string;
        rowCount: number;
        columns: Array<{ id: string; name: string; type: string }>;
    }>;
}): SchemaValidationResult {
    const errors: Array<{ path: string; message: string }> = [];
    const warnings: Array<{ path: string; message: string }> = [];

    // Must have at least one table
    if (!schema.tables || schema.tables.length === 0) {
        errors.push({ path: 'schema', message: 'At least one table is required' });
        return { isValid: false, errors, warnings };
    }

    const tableNames: string[] = [];

    for (const table of schema.tables) {
        const tablePath = `table:${table.name}`;

        // Validate table name
        const tableNameResult = validateTableName(table.name, tableNames);
        if (!tableNameResult.isValid) {
            errors.push({ path: tablePath, message: tableNameResult.error! });
        } else if (tableNameResult.warning) {
            warnings.push({ path: tablePath, message: tableNameResult.warning });
        }
        tableNames.push(table.name);

        // Validate row count
        const rowCountResult = validateRowCount(table.rowCount);
        if (!rowCountResult.isValid) {
            errors.push({ path: `${tablePath}.rowCount`, message: rowCountResult.error! });
        } else if (rowCountResult.warning) {
            warnings.push({ path: `${tablePath}.rowCount`, message: rowCountResult.warning });
        }

        // Must have at least one column
        if (!table.columns || table.columns.length === 0) {
            errors.push({ path: tablePath, message: 'Table must have at least one column' });
            continue;
        }

        const columnNames: string[] = [];

        for (const column of table.columns) {
            const columnPath = `${tablePath}.${column.name}`;

            // Validate column name
            const columnNameResult = validateColumnName(column.name, columnNames, table.name);
            if (!columnNameResult.isValid) {
                errors.push({ path: columnPath, message: columnNameResult.error! });
            } else if (columnNameResult.warning) {
                warnings.push({ path: columnPath, message: columnNameResult.warning });
            }
            columnNames.push(column.name);
        }
    }

    return {
        isValid: errors.length === 0,
        errors,
        warnings,
    };
}
