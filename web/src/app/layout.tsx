import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin", "greek"],
});

export const metadata: Metadata = {
  title: "Find My Lead",
  description: "Κατάλογος ελληνικών επιχειρήσεων με στοιχεία επικοινωνίας",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="el" className={`${inter.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col bg-canvas text-ink font-sans">{children}</body>
    </html>
  );
}
