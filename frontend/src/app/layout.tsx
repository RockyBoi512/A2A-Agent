import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Onboarding Assignment Agent | SAP',
  description: 'MILP-optimized consultant-to-customer assignment with AI recommendations',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="font-sap antialiased">{children}</body>
    </html>
  )
}