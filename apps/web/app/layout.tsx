import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'RecoverOS - AI Revenue Recovery',
  description: 'AI Revenue Recovery Portfolio Optimizer',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
