import type { Metadata } from "next";
import { JetBrains_Mono, Bebas_Neue } from "next/font/google";
import { SmoothScroll } from "@/components/smooth-scroll";
import { AnimatedNoise } from "@/components/animated-noise";
import "./globals.css";

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
});

const bebasNeue = Bebas_Neue({
  weight: "400",
  subsets: ["latin"],
  variable: "--font-bebas-neue",
});

export const metadata: Metadata = {
  title: "Syllogic — Open Source Personal Finance",
  description:
    "Track every transaction. Understand every pattern. Your data stays on your hardware.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${jetbrainsMono.variable} ${bebasNeue.variable}`}
    >
      <body className="font-mono bg-bg text-fg">
        <AnimatedNoise />
        <SmoothScroll>{children}</SmoothScroll>
      </body>
    </html>
  );
}
