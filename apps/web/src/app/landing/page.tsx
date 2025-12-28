"use client";

import Link from 'next/link';
import { ArrowRight, Zap, Database, GitBranch, Shield, Gauge, Sparkles } from 'lucide-react';

const stats = [
    { value: '1M+', label: 'Rows per second' },
    { value: '100%', label: 'FK Integrity' },
    { value: '6', label: 'Export formats' },
];

const features = [
    {
        icon: Database,
        title: 'Visual Schema Builder',
        description: 'Design multi-table schemas with an intuitive drag-and-drop interface. Define columns, types, and relationships visually.',
    },
    {
        icon: Sparkles,
        title: 'AI-Powered Story Mode',
        description: 'Describe your data needs in plain English. Our LLM generates complete schemas with relationships automatically.',
    },
    {
        icon: GitBranch,
        title: 'Perfect Referential Integrity',
        description: 'Foreign key relationships are guaranteed valid. Parent-child ratios are automatically balanced.',
    },
    {
        icon: Shield,
        title: 'Enterprise-Grade Validation',
        description: 'Post-generation validation checks for data quality, distribution accuracy, and business rule compliance.',
    },
    {
        icon: Gauge,
        title: 'ML-Ready Data',
        description: 'Built-in noise injection for nulls, outliers, typos, and temporal drift. Perfect for model training.',
    },
    {
        icon: Zap,
        title: 'Blazing Fast Generation',
        description: 'Streaming architecture generates millions of rows in seconds. No memory bottlenecks.',
    },
];

export default function LandingPage() {
    return (
        <div className="min-h-screen" style={{ background: '#DAD7CD' }}>
            {/* Organic Background Elements */}
            <div className="fixed inset-0 pointer-events-none overflow-hidden">
                <div className="absolute top-[-15%] right-[-10%] w-[600px] h-[600px] rounded-full blur-[150px]" style={{ background: '#A3B18A', opacity: 0.2 }} />
                <div className="absolute bottom-[-10%] left-[-5%] w-[500px] h-[500px] rounded-full blur-[120px]" style={{ background: '#588157', opacity: 0.1 }} />
            </div>

            {/* Navigation */}
            <nav className="relative z-10 border-b" style={{ borderColor: 'rgba(58, 90, 64, 0.15)' }}>
                <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
                    <Link href="/landing" style={{ textDecoration: 'none' }}>
                        <span
                            style={{
                                fontSize: '38px',
                                fontFamily: 'var(--font-pinyon), Pinyon Script, cursive',
                                fontWeight: 400,
                                color: '#3A5A40',
                                letterSpacing: '0.01em',
                                textShadow: '0 0 1px rgba(58, 90, 64, 0.2)'
                            }}
                        >
                            Misata
                        </span>
                    </Link>

                    <div className="flex items-center gap-6">
                        <Link href="/docs" className="text-sm transition-colors" style={{ color: '#4A6B4A' }}>
                            Documentation
                        </Link>
                        <Link href="/templates" className="text-sm transition-colors" style={{ color: '#4A6B4A' }}>
                            Templates
                        </Link>
                        <a
                            href="https://github.com/yourusername/misata"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-sm transition-colors"
                            style={{ color: '#4A6B4A' }}
                        >
                            GitHub
                        </a>
                        <Link href="/" className="btn btn-primary btn-sm">
                            Open Console
                            <ArrowRight className="w-3.5 h-3.5" />
                        </Link>
                    </div>
                </div>
            </nav>

            {/* Hero */}
            <section className="relative z-10 pt-28 pb-24">
                <div className="max-w-4xl mx-auto px-6 text-center">
                    {/* Badge */}
                    <div
                        className="inline-flex items-center gap-2 px-4 py-2 rounded-full mb-10"
                        style={{ background: 'rgba(88, 129, 87, 0.12)', border: '1px solid rgba(88, 129, 87, 0.2)' }}
                    >
                        <span className="w-2 h-2 rounded-full animate-pulse" style={{ background: '#588157' }} />
                        <span className="text-xs font-semibold tracking-wide" style={{ color: '#3A5A40' }}>
                            Free Pilot — No Sign-up Required
                        </span>
                    </div>

                    {/* Headline */}
                    <h1
                        className="text-5xl md:text-6xl font-medium mb-8 leading-tight"
                        style={{ color: '#3A5A40', fontFamily: 'Cormorant Garamond, serif' }}
                    >
                        Generate Production-Ready
                        <br />
                        <span className="text-gradient">Synthetic Data</span>
                    </h1>

                    <p className="text-lg max-w-2xl mx-auto mb-12 leading-relaxed" style={{ color: '#4A6B4A' }}>
                        The AI-powered data generation engine that transforms natural language
                        into statistically accurate, multi-table datasets with perfect referential integrity.
                    </p>

                    {/* CTAs */}
                    <div className="flex items-center justify-center gap-4 mb-20">
                        <Link href="/" className="btn btn-primary btn-lg">
                            Launch Builder
                            <ArrowRight className="w-4 h-4" />
                        </Link>
                        <Link href="/story" className="btn btn-secondary btn-lg">
                            <Sparkles className="w-4 h-4" />
                            Try Story Mode
                        </Link>
                    </div>

                    {/* Stats */}
                    <div className="flex items-center justify-center gap-16">
                        {stats.map((stat) => (
                            <div key={stat.label} className="text-center">
                                <p className="text-4xl font-medium mb-2" style={{ color: '#3A5A40', fontFamily: 'Cormorant Garamond, serif' }}>{stat.value}</p>
                                <p className="text-xs uppercase tracking-widest font-medium" style={{ color: '#6B7164' }}>{stat.label}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* Features */}
            <section className="relative z-10 py-24 border-t" style={{ borderColor: 'rgba(58, 90, 64, 0.15)' }}>
                <div className="max-w-6xl mx-auto px-6">
                    <div className="text-center mb-16">
                        <h2
                            className="text-3xl font-medium mb-4"
                            style={{ color: '#3A5A40', fontFamily: 'Cormorant Garamond, serif' }}
                        >
                            Enterprise-Grade Capabilities
                        </h2>
                        <p className="max-w-xl mx-auto" style={{ color: '#4A6B4A' }}>
                            Built for data scientists, engineers, and teams who need realistic test data at scale.
                        </p>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {features.map((feature) => {
                            const Icon = feature.icon;
                            return (
                                <div
                                    key={feature.title}
                                    className="p-6 rounded-xl transition-all duration-200 hover:-translate-y-1"
                                    style={{
                                        background: '#FEFEFE',
                                        border: '1px solid rgba(58, 90, 64, 0.12)',
                                        boxShadow: '0 4px 12px rgba(58, 90, 64, 0.06)'
                                    }}
                                >
                                    <div
                                        className="w-12 h-12 rounded-xl flex items-center justify-center mb-5"
                                        style={{ background: 'rgba(88, 129, 87, 0.12)' }}
                                    >
                                        <Icon className="w-6 h-6" style={{ color: '#588157' }} />
                                    </div>
                                    <h3 className="text-lg font-semibold mb-3" style={{ color: '#3A5A40' }}>
                                        {feature.title}
                                    </h3>
                                    <p className="text-sm leading-relaxed" style={{ color: '#6B7164' }}>
                                        {feature.description}
                                    </p>
                                </div>
                            );
                        })}
                    </div>
                </div>
            </section>

            {/* CTA Section */}
            <section className="relative z-10 py-24 border-t" style={{ borderColor: 'rgba(58, 90, 64, 0.15)' }}>
                <div className="max-w-2xl mx-auto px-6 text-center">
                    <h2
                        className="text-3xl font-medium mb-4"
                        style={{ color: '#3A5A40', fontFamily: 'Cormorant Garamond, serif' }}
                    >
                        Ready to Generate Perfect Data?
                    </h2>
                    <p className="mb-8" style={{ color: '#4A6B4A' }}>
                        No sign-up required. Start building in seconds.
                    </p>
                    <Link href="/" className="btn btn-primary btn-lg">
                        Get Started
                        <ArrowRight className="w-4 h-4" />
                    </Link>
                </div>
            </section>

            {/* Footer */}
            <footer className="relative z-10 py-8 border-t" style={{ borderColor: 'rgba(58, 90, 64, 0.15)', background: '#344E41' }}>
                <div className="max-w-6xl mx-auto px-6 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <Database className="w-4 h-4" style={{ color: 'rgba(245, 243, 239, 0.5)' }} />
                        <span className="text-sm" style={{ color: 'rgba(245, 243, 239, 0.7)' }}>
                            Misata — v0.1.0-beta
                        </span>
                    </div>
                    <div className="flex items-center gap-6 text-sm" style={{ color: 'rgba(245, 243, 239, 0.5)' }}>
                        <a href="https://pypi.org/project/misata/" target="_blank" rel="noopener noreferrer" className="hover:text-white transition-colors">
                            PyPI
                        </a>
                        <a href="https://github.com" target="_blank" rel="noopener noreferrer" className="hover:text-white transition-colors">
                            GitHub
                        </a>
                    </div>
                </div>
            </footer>
        </div>
    );
}
