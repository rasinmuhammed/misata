"use client";

import { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useSchemaStore, Column, TableNode } from '@/store/schemaStore';
import {
    ShoppingCart,
    BarChart3,
    Stethoscope,
    Landmark,
    Table2,
    Rows3,
    GitBranch,
    ArrowRight,
    Filter
} from 'lucide-react';

interface Template {
    id: string;
    name: string;
    description: string;
    category: 'business' | 'healthcare' | 'finance';
    icon: typeof ShoppingCart;
    tables: { name: string; row_count: number }[];
    columns: Record<string, { name: string; type: string; distribution_params?: Record<string, unknown> }[]>;
    relationships: { parent_table: string; child_table: string; parent_key: string; child_key: string }[];
}

const templates: Template[] = [
    {
        id: 'ecommerce',
        name: 'E-commerce Platform',
        description: 'Complete online retail schema with users, products, orders, and order items.',
        category: 'business',
        icon: ShoppingCart,
        tables: [
            { name: 'users', row_count: 1000 },
            { name: 'products', row_count: 500 },
            { name: 'orders', row_count: 5000 },
            { name: 'order_items', row_count: 15000 },
        ],
        columns: {
            users: [
                { name: 'id', type: 'int', distribution_params: { distribution: 'sequence' } },
                { name: 'name', type: 'text', distribution_params: { distribution: 'fake.name' } },
                { name: 'email', type: 'text', distribution_params: { distribution: 'fake.email' } },
                { name: 'created_at', type: 'date' },
            ],
            products: [
                { name: 'id', type: 'int', distribution_params: { distribution: 'sequence' } },
                { name: 'name', type: 'text' },
                { name: 'category', type: 'categorical', distribution_params: { choices: ['Electronics', 'Clothing', 'Home', 'Sports', 'Books'] } },
                { name: 'price', type: 'float', distribution_params: { distribution: 'uniform', min: 9.99, max: 999.99 } },
            ],
            orders: [
                { name: 'id', type: 'int', distribution_params: { distribution: 'sequence' } },
                { name: 'user_id', type: 'foreign_key', distribution_params: { reference_table: 'users' } },
                { name: 'status', type: 'categorical', distribution_params: { choices: ['pending', 'processing', 'shipped', 'delivered'] } },
                { name: 'total', type: 'float', distribution_params: { distribution: 'uniform', min: 20, max: 500 } },
                { name: 'created_at', type: 'date' },
            ],
            order_items: [
                { name: 'id', type: 'int', distribution_params: { distribution: 'sequence' } },
                { name: 'order_id', type: 'foreign_key', distribution_params: { reference_table: 'orders' } },
                { name: 'product_id', type: 'foreign_key', distribution_params: { reference_table: 'products' } },
                { name: 'quantity', type: 'int', distribution_params: { distribution: 'uniform', min: 1, max: 5 } },
            ],
        },
        relationships: [
            { parent_table: 'users', child_table: 'orders', parent_key: 'id', child_key: 'user_id' },
            { parent_table: 'orders', child_table: 'order_items', parent_key: 'id', child_key: 'order_id' },
            { parent_table: 'products', child_table: 'order_items', parent_key: 'id', child_key: 'product_id' },
        ],
    },
    {
        id: 'saas',
        name: 'SaaS Analytics',
        description: 'B2B SaaS platform with companies, users, subscriptions, and usage events.',
        category: 'business',
        icon: BarChart3,
        tables: [
            { name: 'companies', row_count: 200 },
            { name: 'users', row_count: 2000 },
            { name: 'subscriptions', row_count: 200 },
            { name: 'events', row_count: 50000 },
        ],
        columns: {
            companies: [
                { name: 'id', type: 'int', distribution_params: { distribution: 'sequence' } },
                { name: 'name', type: 'text', distribution_params: { distribution: 'fake.company' } },
                { name: 'industry', type: 'categorical', distribution_params: { choices: ['Technology', 'Finance', 'Healthcare', 'Retail', 'Manufacturing'] } },
                { name: 'employee_count', type: 'int', distribution_params: { distribution: 'uniform', min: 10, max: 10000 } },
            ],
            users: [
                { name: 'id', type: 'int', distribution_params: { distribution: 'sequence' } },
                { name: 'company_id', type: 'foreign_key', distribution_params: { reference_table: 'companies' } },
                { name: 'email', type: 'text', distribution_params: { distribution: 'fake.email' } },
                { name: 'role', type: 'categorical', distribution_params: { choices: ['admin', 'editor', 'viewer'] } },
            ],
            subscriptions: [
                { name: 'id', type: 'int', distribution_params: { distribution: 'sequence' } },
                { name: 'company_id', type: 'foreign_key', distribution_params: { reference_table: 'companies' } },
                { name: 'plan', type: 'categorical', distribution_params: { choices: ['starter', 'professional', 'enterprise'] } },
                { name: 'mrr', type: 'float', distribution_params: { distribution: 'uniform', min: 49, max: 999 } },
            ],
            events: [
                { name: 'id', type: 'int', distribution_params: { distribution: 'sequence' } },
                { name: 'user_id', type: 'foreign_key', distribution_params: { reference_table: 'users' } },
                { name: 'event_type', type: 'categorical', distribution_params: { choices: ['page_view', 'click', 'signup', 'purchase'] } },
                { name: 'event_time', type: 'date' },
            ],
        },
        relationships: [
            { parent_table: 'companies', child_table: 'users', parent_key: 'id', child_key: 'company_id' },
            { parent_table: 'companies', child_table: 'subscriptions', parent_key: 'id', child_key: 'company_id' },
            { parent_table: 'users', child_table: 'events', parent_key: 'id', child_key: 'user_id' },
        ],
    },
    {
        id: 'healthcare',
        name: 'Healthcare System',
        description: 'Hospital management with departments, doctors, patients, and appointments.',
        category: 'healthcare',
        icon: Stethoscope,
        tables: [
            { name: 'departments', row_count: 20 },
            { name: 'doctors', row_count: 100 },
            { name: 'patients', row_count: 5000 },
            { name: 'appointments', row_count: 25000 },
        ],
        columns: {
            departments: [
                { name: 'id', type: 'int', distribution_params: { distribution: 'sequence' } },
                { name: 'name', type: 'categorical', distribution_params: { choices: ['Cardiology', 'Neurology', 'Oncology', 'Pediatrics', 'Orthopedics'] } },
                { name: 'floor', type: 'int', distribution_params: { distribution: 'uniform', min: 1, max: 10 } },
            ],
            doctors: [
                { name: 'id', type: 'int', distribution_params: { distribution: 'sequence' } },
                { name: 'department_id', type: 'foreign_key', distribution_params: { reference_table: 'departments' } },
                { name: 'name', type: 'text', distribution_params: { distribution: 'fake.name' } },
                { name: 'specialty', type: 'text' },
            ],
            patients: [
                { name: 'id', type: 'int', distribution_params: { distribution: 'sequence' } },
                { name: 'name', type: 'text', distribution_params: { distribution: 'fake.name' } },
                { name: 'date_of_birth', type: 'date' },
                { name: 'blood_type', type: 'categorical', distribution_params: { choices: ['A+', 'A-', 'B+', 'B-', 'O+', 'O-', 'AB+', 'AB-'] } },
            ],
            appointments: [
                { name: 'id', type: 'int', distribution_params: { distribution: 'sequence' } },
                { name: 'patient_id', type: 'foreign_key', distribution_params: { reference_table: 'patients' } },
                { name: 'doctor_id', type: 'foreign_key', distribution_params: { reference_table: 'doctors' } },
                { name: 'date', type: 'date' },
                { name: 'status', type: 'categorical', distribution_params: { choices: ['scheduled', 'completed', 'cancelled'] } },
            ],
        },
        relationships: [
            { parent_table: 'departments', child_table: 'doctors', parent_key: 'id', child_key: 'department_id' },
            { parent_table: 'patients', child_table: 'appointments', parent_key: 'id', child_key: 'patient_id' },
            { parent_table: 'doctors', child_table: 'appointments', parent_key: 'id', child_key: 'doctor_id' },
        ],
    },
    {
        id: 'fintech',
        name: 'FinTech Transactions',
        description: 'Financial platform with customers, accounts, and transaction history.',
        category: 'finance',
        icon: Landmark,
        tables: [
            { name: 'customers', row_count: 1000 },
            { name: 'accounts', row_count: 2000 },
            { name: 'transactions', row_count: 100000 },
        ],
        columns: {
            customers: [
                { name: 'id', type: 'int', distribution_params: { distribution: 'sequence' } },
                { name: 'name', type: 'text', distribution_params: { distribution: 'fake.name' } },
                { name: 'email', type: 'text', distribution_params: { distribution: 'fake.email' } },
                { name: 'risk_score', type: 'float', distribution_params: { distribution: 'uniform', min: 0, max: 100 } },
            ],
            accounts: [
                { name: 'id', type: 'int', distribution_params: { distribution: 'sequence' } },
                { name: 'customer_id', type: 'foreign_key', distribution_params: { reference_table: 'customers' } },
                { name: 'account_type', type: 'categorical', distribution_params: { choices: ['checking', 'savings', 'investment'] } },
                { name: 'balance', type: 'float', distribution_params: { distribution: 'uniform', min: 0, max: 100000 } },
            ],
            transactions: [
                { name: 'id', type: 'int', distribution_params: { distribution: 'sequence' } },
                { name: 'account_id', type: 'foreign_key', distribution_params: { reference_table: 'accounts' } },
                { name: 'amount', type: 'float', distribution_params: { distribution: 'normal', mean: 150, std: 500 } },
                { name: 'type', type: 'categorical', distribution_params: { choices: ['deposit', 'withdrawal', 'transfer'] } },
                { name: 'event_time', type: 'date' },
                { name: 'is_fraud', type: 'boolean', distribution_params: { probability: 0.02 } },
            ],
        },
        relationships: [
            { parent_table: 'customers', child_table: 'accounts', parent_key: 'id', child_key: 'customer_id' },
            { parent_table: 'accounts', child_table: 'transactions', parent_key: 'id', child_key: 'account_id' },
        ],
    },
];

const categories = [
    { id: 'all', label: 'All Templates' },
    { id: 'business', label: 'Business' },
    { id: 'healthcare', label: 'Healthcare' },
    { id: 'finance', label: 'Finance' },
];

export default function TemplatesPage() {
    const router = useRouter();
    const { addTable, addRelationship, clearSchema } = useSchemaStore();
    const [selectedCategory, setSelectedCategory] = useState('all');

    const filteredTemplates = templates.filter(
        t => selectedCategory === 'all' || t.category === selectedCategory
    );

    const handleUseTemplate = useCallback((template: Template) => {
        // Clear existing schema before loading template
        clearSchema();

        const tableIdMap: Record<string, string> = {};

        template.tables.forEach((tableData, index) => {
            const tableId = `table_${Date.now()}_${index}`;
            tableIdMap[tableData.name] = tableId;

            const columns: Column[] = (template.columns[tableData.name] || []).map(
                (col, colIdx) => ({
                    id: `col_${Date.now()}_${index}_${colIdx}`,
                    name: col.name,
                    type: col.type as Column['type'],
                    distributionParams: col.distribution_params,
                })
            );

            const newTable: TableNode = {
                id: tableId,
                name: tableData.name,
                rowCount: tableData.row_count,
                columns,
                position: {
                    x: 100 + (index % 3) * 350,
                    y: 100 + Math.floor(index / 3) * 300,
                },
            };

            addTable(newTable);
        });

        template.relationships.forEach((rel, index) => {
            addRelationship({
                id: `rel_${Date.now()}_${index}`,
                sourceTable: tableIdMap[rel.parent_table],
                sourceColumn: rel.parent_key,
                targetTable: tableIdMap[rel.child_table],
                targetColumn: rel.child_key,
            });
        });

        router.push('/builder');
    }, [addTable, addRelationship, clearSchema, router]);

    return (
        <div className="p-8 max-w-6xl mx-auto animate-fade-in">
            {/* Header */}
            <div className="mb-8">
                <h1 className="text-heading text-[var(--text-primary)] mb-2">
                    Schema Templates
                </h1>
                <p className="text-body">
                    Pre-built schemas for common use cases. Click to import into the builder.
                </p>
            </div>

            {/* Filters */}
            <div className="flex items-center gap-2 mb-8">
                <Filter className="w-4 h-4 text-[var(--text-muted)]" />
                {categories.map((cat) => (
                    <button
                        key={cat.id}
                        onClick={() => setSelectedCategory(cat.id)}
                        className={`btn btn-sm ${selectedCategory === cat.id ? 'btn-primary' : 'btn-ghost'
                            }`}
                    >
                        {cat.label}
                    </button>
                ))}
            </div>

            {/* Templates Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {filteredTemplates.map((template) => {
                    const Icon = template.icon;
                    const totalRows = template.tables.reduce((sum, t) => sum + t.row_count, 0);

                    return (
                        <div
                            key={template.id}
                            className="card p-6 hover:border-[var(--border-default)] transition-all group"
                        >
                            <div className="flex items-start gap-4">
                                <div className="w-12 h-12 rounded-lg bg-[var(--accent-muted)] flex items-center justify-center flex-shrink-0 group-hover:bg-[var(--brand-primary)]/20 transition-colors">
                                    <Icon className="w-6 h-6 text-[var(--brand-primary-light)]" />
                                </div>
                                <div className="flex-1 min-w-0">
                                    <h3 className="text-title text-[var(--text-primary)] mb-1">
                                        {template.name}
                                    </h3>
                                    <p className="text-sm text-[var(--text-secondary)] mb-4 line-clamp-2">
                                        {template.description}
                                    </p>

                                    {/* Stats */}
                                    <div className="flex items-center gap-4 mb-4">
                                        <div className="flex items-center gap-1.5 text-xs text-[var(--text-tertiary)]">
                                            <Table2 className="w-3.5 h-3.5" />
                                            <span>{template.tables.length} tables</span>
                                        </div>
                                        <div className="flex items-center gap-1.5 text-xs text-[var(--text-tertiary)]">
                                            <Rows3 className="w-3.5 h-3.5" />
                                            <span>{totalRows.toLocaleString()} rows</span>
                                        </div>
                                        <div className="flex items-center gap-1.5 text-xs text-[var(--text-tertiary)]">
                                            <GitBranch className="w-3.5 h-3.5" />
                                            <span>{template.relationships.length} relations</span>
                                        </div>
                                    </div>

                                    {/* Action */}
                                    <button
                                        onClick={() => handleUseTemplate(template)}
                                        className="btn btn-secondary btn-sm"
                                    >
                                        Use Template
                                        <ArrowRight className="w-3.5 h-3.5" />
                                    </button>
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
