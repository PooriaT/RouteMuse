import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "RouteMuse", description: "Personalized outdoor route planning" };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="en" suppressHydrationWarning><body>{children}</body></html>; }
