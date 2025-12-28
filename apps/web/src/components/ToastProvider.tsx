"use client";

import { createContext, useContext, useState, useCallback, ReactNode } from 'react';
import { CheckCircle, XCircle, Info, AlertTriangle, X } from 'lucide-react';

interface Toast {
    id: string;
    message: string;
    type: 'success' | 'error' | 'info' | 'warning';
    duration?: number;
}

interface ToastContextType {
    toasts: Toast[];
    addToast: (message: string, type?: Toast['type'], duration?: number) => void;
    removeToast: (id: string) => void;
}

const ToastContext = createContext<ToastContextType | null>(null);

export function useToast() {
    const context = useContext(ToastContext);
    if (!context) {
        throw new Error('useToast must be used within ToastProvider');
    }
    return context;
}

const toastConfig: Record<Toast['type'], {
    icon: typeof CheckCircle;
    bg: string;
    border: string;
    iconColor: string
}> = {
    success: {
        icon: CheckCircle,
        bg: 'bg-[var(--success-muted)]',
        border: 'border-[var(--success)]/30',
        iconColor: 'text-[var(--success)]',
    },
    error: {
        icon: XCircle,
        bg: 'bg-[var(--error-muted)]',
        border: 'border-[var(--error)]/30',
        iconColor: 'text-[var(--error)]',
    },
    info: {
        icon: Info,
        bg: 'bg-[var(--info-muted)]',
        border: 'border-[var(--info)]/30',
        iconColor: 'text-[var(--info)]',
    },
    warning: {
        icon: AlertTriangle,
        bg: 'bg-[var(--warning-muted)]',
        border: 'border-[var(--warning)]/30',
        iconColor: 'text-[var(--warning)]',
    },
};

function ToastItem({ toast, onRemove }: { toast: Toast; onRemove: () => void }) {
    const config = toastConfig[toast.type];
    const Icon = config.icon;

    return (
        <div
            className={`
                flex items-center gap-3 px-4 py-3 rounded-lg shadow-lg
                ${config.bg} ${config.border} border backdrop-blur-sm
                animate-fade-in
            `}
        >
            <Icon className={`w-4 h-4 ${config.iconColor} flex-shrink-0`} />
            <p className="text-sm text-[var(--text-primary)] flex-1">{toast.message}</p>
            <button
                onClick={onRemove}
                className="text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
            >
                <X className="w-3.5 h-3.5" />
            </button>
        </div>
    );
}

export function ToastProvider({ children }: { children: ReactNode }) {
    const [toasts, setToasts] = useState<Toast[]>([]);

    const addToast = useCallback((
        message: string,
        type: Toast['type'] = 'info',
        duration: number = 5000
    ) => {
        const id = `toast_${Date.now()}`;
        const newToast: Toast = { id, message, type, duration };

        setToasts((prev) => [...prev, newToast]);

        if (duration > 0) {
            setTimeout(() => {
                setToasts((prev) => prev.filter((t) => t.id !== id));
            }, duration);
        }
    }, []);

    const removeToast = useCallback((id: string) => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
    }, []);

    return (
        <ToastContext.Provider value={{ toasts, addToast, removeToast }}>
            {children}

            {/* Toast Container */}
            <div className="fixed bottom-4 right-4 z-50 space-y-2 max-w-sm">
                {toasts.map((toast) => (
                    <ToastItem
                        key={toast.id}
                        toast={toast}
                        onRemove={() => removeToast(toast.id)}
                    />
                ))}
            </div>
        </ToastContext.Provider>
    );
}
