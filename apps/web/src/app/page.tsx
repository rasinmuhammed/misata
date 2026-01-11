"use client";

import { useRouter } from 'next/navigation';
import {
  Sparkles,
  Layers,
  LayoutGrid,
  TrendingUp,
  Zap,
  Database,
  GitBranch,
  ArrowRight,
  Play,
  Brain,
  Target,
  BarChart3
} from 'lucide-react';

const features = [
  {
    icon: Sparkles,
    title: 'AI Story Mode',
    description: 'Describe your data in plain English. Our AI generates complete schemas instantly.',
    color: '#588157',
    href: '/story'
  },
  {
    icon: Layers,
    title: 'Visual Schema Builder',
    description: 'Drag-and-drop tables, define columns, and visualize relationships in real-time.',
    color: '#5B8A8A',
    href: '/builder'
  },
  {
    icon: LayoutGrid,
    title: 'Industry Templates',
    description: 'Start with pre-built schemas for e-commerce, SaaS, healthcare, and finance.',
    color: '#D4A574',
    href: '/templates'
  },
  {
    icon: TrendingUp,
    title: 'Outcome Constraints',
    description: 'Draw revenue curves and let our engine reverse-engineer matching transactions.',
    color: '#3A5A40',
    href: '/builder'
  },
];

const stats = [
  { value: '50+', label: 'Entity Types' },
  { value: '1M+', label: 'Rows/Second' },
  { value: '100%', label: 'Referential Integrity' },
  { value: '∞', label: 'Customization' },
];

export default function HomePage() {
  const router = useRouter();

  return (
    <div className="min-h-screen overflow-auto" style={{ background: '#FAF9F6' }}>
      {/* Hero Section */}
      <div className="relative overflow-hidden">
        {/* Decorative background elements */}
        <div
          className="absolute inset-0 opacity-30"
          style={{
            background: 'radial-gradient(ellipse at 20% 20%, rgba(88, 129, 87, 0.15) 0%, transparent 50%), radial-gradient(ellipse at 80% 80%, rgba(58, 90, 64, 0.1) 0%, transparent 50%)'
          }}
        />

        <div className="relative max-w-6xl mx-auto px-8 pt-16 pb-20">
          {/* Badge */}
          <div className="flex justify-center mb-8">
            <div
              className="inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm"
              style={{ background: 'rgba(88, 129, 87, 0.1)', color: '#3A5A40' }}
            >
              <Zap className="w-4 h-4" />
              <span className="font-medium">AI-Powered Synthetic Data Engine</span>
            </div>
          </div>

          {/* Main Headline */}
          <h1
            className="text-center text-5xl md:text-6xl font-serif mb-6"
            style={{
              color: '#344E41',
              fontFamily: 'var(--font-cormorant), Cormorant Garamond, serif',
              fontWeight: 600,
              lineHeight: 1.2
            }}
          >
            Generate realistic data<br />
            <span style={{ color: '#588157' }}>in seconds, not days</span>
          </h1>

          {/* Subheadline */}
          <p
            className="text-center text-lg max-w-2xl mx-auto mb-10"
            style={{ color: '#6B7164' }}
          >
            Build multi-table datasets with complex relationships, statistical distributions,
            and business-realistic patterns. No more manual data creation for testing, demos, or ML training.
          </p>

          {/* CTA Buttons */}
          <div className="flex justify-center gap-4 mb-16">
            <button
              onClick={() => router.push('/workspace')}
              className="flex items-center gap-2 px-6 py-3 rounded-xl text-white font-medium transition-all hover:scale-105 shadow-lg"
              style={{
                background: 'linear-gradient(135deg, #588157 0%, #3A5A40 100%)',
                boxShadow: '0 4px 20px rgba(58, 90, 64, 0.3)'
              }}
            >
              <Play className="w-4 h-4" />
              Open MisataStudio
            </button>
            <button
              onClick={() => router.push('/workspace')}
              className="flex items-center gap-2 px-6 py-3 rounded-xl font-medium transition-all hover:scale-105"
              style={{
                background: '#FFF',
                color: '#3A5A40',
                border: '1px solid rgba(58, 90, 64, 0.2)',
                boxShadow: '0 2px 10px rgba(0, 0, 0, 0.05)'
              }}
            >
              <Layers className="w-4 h-4" />
              View Documentation
            </button>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-4 gap-6 max-w-3xl mx-auto">
            {stats.map((stat, i) => (
              <div key={i} className="text-center">
                <div
                  className="text-3xl font-bold mb-1"
                  style={{ color: '#3A5A40' }}
                >
                  {stat.value}
                </div>
                <div className="text-sm" style={{ color: '#8B9185' }}>
                  {stat.label}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Features Section */}
      <div className="max-w-6xl mx-auto px-8 py-16">
        <div className="text-center mb-12">
          <h2
            className="text-3xl font-serif mb-3"
            style={{
              color: '#344E41',
              fontFamily: 'var(--font-cormorant), Cormorant Garamond, serif',
              fontWeight: 600
            }}
          >
            Multiple ways to create your data
          </h2>
          <p style={{ color: '#6B7164' }}>
            Choose the workflow that fits your needs
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {features.map((feature, i) => {
            const Icon = feature.icon;
            return (
              <button
                key={i}
                onClick={() => router.push(feature.href)}
                className="text-left p-6 rounded-2xl transition-all hover:scale-[1.02] group"
                style={{
                  background: '#FFF',
                  border: '1px solid rgba(58, 90, 64, 0.1)',
                  boxShadow: '0 2px 20px rgba(0, 0, 0, 0.03)'
                }}
              >
                <div className="flex items-start gap-4">
                  <div
                    className="w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0"
                    style={{ background: `${feature.color}15` }}
                  >
                    <Icon className="w-6 h-6" style={{ color: feature.color }} />
                  </div>
                  <div className="flex-1">
                    <h3
                      className="text-lg font-semibold mb-1 flex items-center gap-2"
                      style={{ color: '#344E41' }}
                    >
                      {feature.title}
                      <ArrowRight className="w-4 h-4 opacity-0 group-hover:opacity-100 transition-opacity" style={{ color: feature.color }} />
                    </h3>
                    <p className="text-sm" style={{ color: '#6B7164' }}>
                      {feature.description}
                    </p>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* How It Works Section */}
      <div
        className="py-16"
        style={{ background: 'rgba(218, 215, 205, 0.2)' }}
      >
        <div className="max-w-6xl mx-auto px-8">
          <div className="text-center mb-12">
            <h2
              className="text-3xl font-serif mb-3"
              style={{
                color: '#344E41',
                fontFamily: 'var(--font-cormorant), Cormorant Garamond, serif',
                fontWeight: 600
              }}
            >
              How it works
            </h2>
          </div>

          <div className="grid grid-cols-3 gap-8">
            {[
              { step: '01', icon: Brain, title: 'Define Your Schema', desc: 'Use AI, templates, or build manually. Define tables, columns, and relationships.' },
              { step: '02', icon: Target, title: 'Set Constraints', desc: 'Add outcome curves, distribution rules, and business logic constraints.' },
              { step: '03', icon: BarChart3, title: 'Generate & Export', desc: 'Generate millions of rows that respect all constraints. Export as CSV or Parquet.' },
            ].map((item, i) => {
              const Icon = item.icon;
              return (
                <div key={i} className="text-center">
                  <div className="relative inline-block mb-4">
                    <div
                      className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto"
                      style={{ background: '#FFF', border: '1px solid rgba(58, 90, 64, 0.1)' }}
                    >
                      <Icon className="w-7 h-7" style={{ color: '#588157' }} />
                    </div>
                    <span
                      className="absolute -top-2 -right-2 text-xs font-bold px-2 py-0.5 rounded-full"
                      style={{ background: '#588157', color: '#FFF' }}
                    >
                      {item.step}
                    </span>
                  </div>
                  <h3 className="font-semibold mb-2" style={{ color: '#344E41' }}>
                    {item.title}
                  </h3>
                  <p className="text-sm" style={{ color: '#6B7164' }}>
                    {item.desc}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Bottom CTA */}
      <div className="max-w-6xl mx-auto px-8 py-16 text-center">
        <div
          className="p-10 rounded-3xl"
          style={{
            background: 'linear-gradient(135deg, #344E41 0%, #3A5A40 100%)',
            boxShadow: '0 20px 60px rgba(52, 78, 65, 0.3)'
          }}
        >
          <h2
            className="text-3xl text-white font-serif mb-4"
            style={{ fontFamily: 'var(--font-cormorant), Cormorant Garamond, serif', fontWeight: 600 }}
          >
            Ready to generate your first dataset?
          </h2>
          <p className="text-white/70 mb-6 max-w-lg mx-auto">
            Start with a simple story and watch Misata transform it into a complete, production-ready dataset.
          </p>
          <button
            onClick={() => router.push('/workspace')}
            className="inline-flex items-center gap-2 px-8 py-3 rounded-xl font-medium transition-all hover:scale-105"
            style={{ background: '#FFF', color: '#344E41' }}
          >
            <Sparkles className="w-4 h-4" />
            Launch MisataStudio
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
