import { NextResponse } from 'next/server'

export async function GET() {
  return NextResponse.json({
    status: 'ok',
    api: 'online',
    database: 'disconnected',
    database_latency_ms: -1,
    version: '0.1.0',
    counts: {
      events: 10500,
      customers: 5000,
      merchants: 100,
    },
  })
}
