import { NextResponse } from 'next/server'
import random from 'crypto'

export async function GET() {
  // Generate dynamic values with random variation
  const baseLiveEvents = 10500
  const baseRecoveryEligible = 10150
  const baseRiskExposure = 6629297276
  const baseHighValueEvents = 225
  const baseLowValueFriction = 1441
  const baseFatiguedAccounts = 929

  const variation = () => 0.95 + Math.random() * 0.1

  return NextResponse.json({
    live_events: Math.floor(baseLiveEvents * variation()),
    recovery_eligible: Math.floor(baseRecoveryEligible * variation()),
    risk_exposure_minor: Math.floor(baseRiskExposure * variation()),
    currency: 'INR',
    high_value_events: Math.floor(baseHighValueEvents * variation()),
    low_value_friction: Math.floor(baseLowValueFriction * variation()),
    fatigued_accounts: Math.floor(baseFatiguedAccounts * variation()),
    database_status: 'disconnected',
  })
}
