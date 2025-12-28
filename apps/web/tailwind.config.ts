/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./src/**/*.{js,ts,jsx,tsx,mdx}",
    ],
    darkMode: "class",
    theme: {
        extend: {
            colors: {
                brand: {
                    primary: '#6366f1',
                    'primary-light': '#818cf8',
                    'primary-dark': '#4f46e5',
                },
                bg: {
                    primary: '#09090b',
                    secondary: '#0f0f12',
                    tertiary: '#18181b',
                    elevated: '#1f1f23',
                },
                border: {
                    subtle: '#3f3f46',
                    default: '#52525b',
                    emphasis: '#71717a',
                },
            },
            borderRadius: {
                DEFAULT: '0.5rem',
            },
        },
    },
    plugins: [],
};
