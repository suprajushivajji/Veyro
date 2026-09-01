'use client'

import { useEffect, useState } from 'react'

interface HealthData {
  status: string
  api: string
  database: string
  database_latency_ms: number
  version: string
  counts: {
    events: number
    customers: number
    merchants: number
  }
}

interface DashboardData {
  live_events: number
  recovery_eligible: number
  risk_exposure_minor: number
  currency: string
  high_value_events: number
  low_value_friction: number
  fatigued_accounts: number
  database_status: string
}

interface EventMixData {
  [key: string]: {
    count: number
    exposure_minor: number
  }
}

interface PaymentMethodsData {
  [key: string]: {
    exposure_minor: number
  }
}

interface SignalsData {
  high_value_events: number
  low_value_friction: number
  fatigued_accounts: number
}

type LoadingState = 'loading' | 'success' | 'error'

export default function Home() {
  const [health, setHealth] = useState<HealthData | null>(null)
  const [dashboard, setDashboard] = useState<DashboardData | null>(null)
  const [eventMix, setEventMix] = useState<EventMixData | null>(null)
  const [paymentMethods, setPaymentMethods] = useState<PaymentMethodsData | null>(null)
  const [signals, setSignals] = useState<SignalsData | null>(null)
  const [loadingState, setLoadingState] = useState<LoadingState>('loading')
  const [error, setError] = useState<string | null>(null)

  const API_URL = process.env.NEXT_PUBLIC_API_URL || ''

  useEffect(() => {
    const fetchData = async () => {
      try {
        setError(null)
        const [healthRes, dashboardRes, eventMixRes, paymentMethodsRes, signalsRes] = await Promise.all([
          fetch(`${API_URL}/api/health`),
          fetch(`${API_URL}/api/dashboard`),
          fetch(`${API_URL}/api/dashboard/event-mix`),
          fetch(`${API_URL}/api/dashboard/payment-methods`),
          fetch(`${API_URL}/api/dashboard/signals`),
        ])

        if (!healthRes.ok) throw new Error('Health endpoint failed')
        if (!dashboardRes.ok) throw new Error('Dashboard endpoint failed')
        if (!eventMixRes.ok) throw new Error('Event mix endpoint failed')
        if (!paymentMethodsRes.ok) throw new Error('Payment methods endpoint failed')
        if (!signalsRes.ok) throw new Error('Signals endpoint failed')

        setHealth(await healthRes.json())
        setDashboard(await dashboardRes.json())
        setEventMix(await eventMixRes.json())
        setPaymentMethods(await paymentMethodsRes.json())
        setSignals(await signalsRes.json())
        setLoadingState('success')
      } catch (err) {
        console.error('Failed to fetch data:', err)
        setError(err instanceof Error ? err.message : 'Failed to connect to API')
        setLoadingState('error')
      }
    }

    fetchData()
    const interval = setInterval(fetchData, 3000) // Refresh every 3 seconds
    return () => clearInterval(interval)
  }, [API_URL])

  const formatCurrency = (paise: number) => {
    return `₹${(paise / 100).toLocaleString('en-IN')}`
  }

  const formatNumber = (num: number) => {
    return num.toLocaleString('en-IN')
  }

  if (loadingState === 'loading') {
    return (
      <main className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
        <div className="container mx-auto px-4 py-16">
          <div className="text-center">
            <h1 className="text-6xl font-bold text-gray-900 mb-4">Veyro</h1>
            <p className="text-xl text-gray-600 mb-8">AI Revenue Recovery Portfolio Optimizer</p>
            <div className="bg-white rounded-lg shadow-lg p-8 max-w-2xl mx-auto">
              <p className="text-gray-600">Loading revenue events...</p>
            </div>
          </div>
        </div>
      </main>
    )
  }

  if (loadingState === 'error') {
    return (
      <main className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
        <div className="container mx-auto px-4 py-16">
          <div className="text-center">
            <h1 className="text-6xl font-bold text-gray-900 mb-4">Veyro</h1>
            <p className="text-xl text-gray-600 mb-8">AI Revenue Recovery Portfolio Optimizer</p>
            <div className="bg-red-50 border border-red-200 rounded-lg shadow-lg p-8 max-w-2xl mx-auto">
              <h2 className="text-2xl font-semibold text-red-800 mb-4">Unable to connect to API</h2>
              <p className="text-red-600 mb-4">{error}</p>
              <p className="text-sm text-red-500">API Endpoint: {API_URL}</p>
              <button 
                onClick={() => window.location.reload()}
                className="mt-4 px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700"
              >
                Retry
              </button>
            </div>
          </div>
        </div>
      </main>
    )
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      <div className="container mx-auto px-4 py-16">
        <div className="text-center">
          <h1 className="text-6xl font-bold text-gray-900 mb-4">Veyro</h1>
          <p className="text-xl text-gray-600 mb-8">AI Revenue Recovery Portfolio Optimizer</p>
          
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {/* Live Events */}
            <div className="bg-white rounded-lg shadow-lg p-4">
              <h2 className="text-sm font-semibold text-gray-800 mb-1">Live Events</h2>
              <div className="text-3xl font-bold text-blue-600">
                {formatNumber(dashboard?.live_events || 0)}
              </div>
              <p className="text-xs text-gray-500">Revenue events in pipeline</p>
            </div>

            {/* Recovery Eligible */}
            <div className="bg-white rounded-lg shadow-lg p-4">
              <h2 className="text-sm font-semibold text-gray-800 mb-1">Recovery Eligible</h2>
              <div className="text-3xl font-bold text-green-600">
                {formatNumber(dashboard?.recovery_eligible || 0)}
              </div>
              <p className="text-xs text-gray-500">Available for intervention</p>
            </div>

            {/* Risk Exposure */}
            <div className="bg-white rounded-lg shadow-lg p-4">
              <h2 className="text-sm font-semibold text-gray-800 mb-1">Risk Exposure</h2>
              <div className="text-3xl font-bold text-red-600">
                {formatCurrency(dashboard?.risk_exposure_minor || 0)}
              </div>
              <p className="text-xs text-gray-500">Estimated value at risk</p>
            </div>

            {/* High-value Events */}
            <div className="bg-white rounded-lg shadow-lg p-4">
              <h2 className="text-sm font-semibold text-gray-800 mb-1">High-value Events</h2>
              <div className="text-3xl font-bold text-blue-600">
                {formatNumber(signals?.high_value_events || 0)}
              </div>
              <p className="text-xs text-gray-500">Events ≥ ₹50,000</p>
            </div>

            {/* Low-value Friction */}
            <div className="bg-white rounded-lg shadow-lg p-4">
              <h2 className="text-sm font-semibold text-gray-800 mb-1">Low-value Friction</h2>
              <div className="text-3xl font-bold text-yellow-600">
                {formatNumber(signals?.low_value_friction || 0)}
              </div>
              <p className="text-xs text-gray-500">Low amount, high friction</p>
            </div>

            {/* Fatigued Accounts */}
            <div className="bg-white rounded-lg shadow-lg p-4">
              <h2 className="text-sm font-semibold text-gray-800 mb-1">Fatigued Accounts</h2>
              <div className="text-3xl font-bold text-purple-600">
                {formatNumber(signals?.fatigued_accounts || 0)}
              </div>
              <p className="text-xs text-gray-500">Accounts with ≥2 contacts</p>
            </div>

            {/* Database Status */}
            <div className="bg-white rounded-lg shadow-lg p-4">
              <h2 className="text-sm font-semibold text-gray-800 mb-1">Database</h2>
              <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                dashboard?.database_status === 'connected' ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'
              }`}>
                {dashboard?.database_status === 'connected' ? 'Online' : 'Offline'}
              </span>
            </div>

            {/* Event Mix - Compact */}
            <div className="bg-white rounded-lg shadow-lg p-4 md:col-span-2">
              <h2 className="text-sm font-semibold text-gray-800 mb-2">Event Mix</h2>
              <div className="grid grid-cols-2 gap-2">
                {Object.entries(eventMix || {}).map(([type, data]) => (
                  <div key={type} className="bg-gray-50 rounded p-2">
                    <div className="text-xs text-gray-600">{type.replace(/_/g, ' ')}</div>
                    <div className="font-semibold text-sm">{formatNumber(data.count)}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Payment Methods - Compact */}
            <div className="bg-white rounded-lg shadow-lg p-4 md:col-span-3">
              <h2 className="text-sm font-semibold text-gray-800 mb-2">Payment Methods</h2>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
                {Object.entries(paymentMethods || {}).map(([method, data]) => (
                  <div key={method} className="bg-gray-50 rounded p-2 text-center">
                    <div className="text-xs text-gray-600">{method}</div>
                    <div className="font-semibold text-sm">{formatCurrency(data.exposure_minor)}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  )
}
