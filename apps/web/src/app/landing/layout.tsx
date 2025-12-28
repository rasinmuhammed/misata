import type { Metadata } from "next";

export const metadata: Metadata = {
    title: "Misata - AI-Powered Synthetic Data Engine",
    description: "Generate realistic multi-table datasets from natural language stories",
};

export default function LandingLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    // Landing page has its own full-width layout without sidebar
    return <>{children}</>;
}
