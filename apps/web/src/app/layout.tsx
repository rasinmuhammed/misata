import type { Metadata } from "next";
import { Cormorant_Garamond, Karla, JetBrains_Mono, Pinyon_Script, Cinzel } from "next/font/google";
import "./globals.css";
import { ToastProvider } from "@/components/ToastProvider";
import ConditionalLayout from "@/components/ConditionalLayout";

const cormorant = Cormorant_Garamond({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-cormorant",
  display: "swap",
});

const karla = Karla({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-karla",
  display: "swap",
});

const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-jetbrains",
  display: "swap",
});

const pinyon = Pinyon_Script({
  subsets: ["latin"],
  weight: "400",
  variable: "--font-pinyon",
  display: "swap",
});

const cinzel = Cinzel({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-cinzel",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Misata - AI-Powered Synthetic Data Engine",
  description: "Generate realistic multi-table datasets from natural language stories",
  keywords: ["synthetic data", "AI", "machine learning", "data generation"],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${cormorant.variable} ${karla.variable} ${jetbrains.variable} ${pinyon.variable} ${cinzel.variable} font-sans antialiased`} suppressHydrationWarning>
        <ToastProvider>
          <ConditionalLayout>
            {children}
          </ConditionalLayout>
        </ToastProvider>
      </body>
    </html>
  );
}
