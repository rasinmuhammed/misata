"use client";

import { usePathname } from 'next/navigation';
import { useState, useEffect } from 'react';
import Sidebar from './Sidebar';

const fullWidthRoutes = ['/landing'];

export default function ConditionalLayout({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();
    const [mounted, setMounted] = useState(false);

    useEffect(() => {
        setMounted(true);
    }, []);

    const isFullWidth = fullWidthRoutes.some(route => pathname?.startsWith(route));

    // During SSR and initial hydration, render the sidebar layout to match server
    if (!mounted) {
        return (
            <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
                <Sidebar />
                <main style={{ flex: 1, overflow: 'auto', background: '#DAD7CD' }}>
                    {children}
                </main>
            </div>
        );
    }

    if (isFullWidth) {
        return <>{children}</>;
    }

    return (
        <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
            <Sidebar />
            <main style={{ flex: 1, overflow: 'auto', background: '#DAD7CD' }}>
                {children}
            </main>
        </div>
    );
}
