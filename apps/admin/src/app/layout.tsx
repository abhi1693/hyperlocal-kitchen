import type { Metadata } from "next";
import { Providers } from "@/components/molecules/providers";
import "./globals.css";
export const metadata: Metadata = {
  title: {
    default: "Hyperlocal Kitchen Admin",
    template: "%s · Hyperlocal Kitchen",
  },
  description: "Community kitchen administration",
  robots: { index: false, follow: false },
};
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
