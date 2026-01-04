"use client";

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import { checkApiHealth } from '@/lib/api';
import {
    Layers,
    Sparkles,
    LayoutGrid,
    Activity,
    FileText,
    Settings,
    CheckCircle,
    XCircle,
    Loader2
} from 'lucide-react';

const navItems = [
    { href: '/builder', label: 'Schema Builder', icon: Layers },
    { href: '/story', label: 'Story Mode', icon: Sparkles },
    { href: '/templates', label: 'Templates', icon: LayoutGrid },
    { href: '/jobs', label: 'Jobs', icon: Activity },
    { href: '/docs', label: 'Documentation', icon: FileText },
    { href: '/settings', label: 'Settings', icon: Settings },
];

export default function Sidebar() {
    const pathname = usePathname();
    const [apiStatus, setApiStatus] = useState<'checking' | 'connected' | 'disconnected'>('checking');

    useEffect(() => {
        const checkStatus = async () => {
            const isHealthy = await checkApiHealth();
            setApiStatus(isHealthy ? 'connected' : 'disconnected');
        };

        checkStatus();
        const interval = setInterval(checkStatus, 15000);
        return () => clearInterval(interval);
    }, []);

    return (
        <aside
            style={{
                width: '256px',
                minWidth: '256px',
                height: '100vh',
                display: 'flex',
                flexDirection: 'column',
                background: '#344E41',
                flexShrink: 0
            }}
        >
            {/* Logo */}
            <div
                style={{
                    height: '64px',
                    display: 'flex',
                    alignItems: 'center',
                    padding: '0 24px',
                    borderBottom: '1px solid rgba(255,255,255,0.1)'
                }}
            >
                <Link href="/" style={{ textDecoration: 'none', display: 'flex', alignItems: 'baseline', gap: '6px' }}>
                    <span
                        style={{
                            fontSize: '32px',
                            fontFamily: 'var(--font-pinyon), Pinyon Script, cursive',
                            fontWeight: 400,
                            color: 'rgba(255,255,255,0.98)',
                            letterSpacing: '0.01em',
                            textShadow: '0 0 1px rgba(255,255,255,0.3)'
                        }}
                    >
                        Misata
                    </span>
                    <span
                        style={{
                            fontSize: '14px',
                            fontFamily: 'var(--font-cinzel), Cinzel, serif',
                            fontWeight: 500,
                            color: 'rgba(255,255,255,0.7)',
                            letterSpacing: '0.15em',
                            textTransform: 'uppercase'
                        }}
                    >
                        Studio
                    </span>
                </Link>
            </div>

            {/* Navigation */}
            <nav style={{ flex: 1, padding: '16px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                {navItems.map((item) => {
                    const isActive = pathname === item.href;
                    const Icon = item.icon;

                    return (
                        <Link
                            key={item.href}
                            href={item.href}
                            style={{
                                position: 'relative',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '12px',
                                padding: '12px 16px',
                                borderRadius: '8px',
                                fontSize: '14px',
                                fontWeight: 500,
                                textDecoration: 'none',
                                transition: 'all 0.2s',
                                color: isActive ? 'white' : 'rgba(255,255,255,0.6)',
                                background: isActive ? 'rgba(255,255,255,0.15)' : 'transparent'
                            }}
                        >
                            {isActive && (
                                <div
                                    style={{
                                        position: 'absolute',
                                        left: 0,
                                        top: '50%',
                                        transform: 'translateY(-50%)',
                                        width: '3px',
                                        height: '24px',
                                        borderRadius: '0 4px 4px 0',
                                        background: '#588157'
                                    }}
                                />
                            )}
                            <Icon style={{ width: '18px', height: '18px' }} strokeWidth={isActive ? 2 : 1.5} />
                            {item.label}
                        </Link>
                    );
                })}
            </nav>

            {/* API Status */}
            <div style={{ padding: '16px', borderTop: '1px solid rgba(255,255,255,0.1)' }}>
                <div
                    style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '10px',
                        padding: '10px 16px',
                        borderRadius: '8px',
                        background: 'rgba(255,255,255,0.08)'
                    }}
                >
                    {apiStatus === 'checking' ? (
                        <Loader2 style={{ width: '14px', height: '14px', color: 'rgba(255,255,255,0.4)' }} className="animate-spin" />
                    ) : apiStatus === 'connected' ? (
                        <CheckCircle style={{ width: '14px', height: '14px', color: '#4ade80' }} />
                    ) : (
                        <XCircle style={{ width: '14px', height: '14px', color: '#f87171' }} />
                    )}
                    <span
                        style={{
                            fontSize: '12px',
                            fontWeight: 500,
                            color: apiStatus === 'connected' ? '#4ade80' :
                                apiStatus === 'disconnected' ? '#f87171' :
                                    'rgba(255,255,255,0.4)'
                        }}
                    >
                        {apiStatus === 'checking' ? 'Checking...' :
                            apiStatus === 'connected' ? 'API Connected' : 'API Disconnected'}
                    </span>
                </div>
            </div>

            {/* Version */}
            <div style={{ padding: '16px 24px', borderTop: '1px solid rgba(255,255,255,0.1)' }}>
                <p
                    style={{
                        fontSize: '10px',
                        color: 'rgba(255,255,255,0.3)',
                        textTransform: 'uppercase',
                        letterSpacing: '0.1em',
                        fontWeight: 500
                    }}
                >
                    v0.1.0-beta
                </p>
            </div>
        </aside>
    );
}
