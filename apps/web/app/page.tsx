'use client'

import { useEffect, useMemo, useState } from 'react'

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

const eventPalette: Record<string, string> = {
  payment_failure: '#8b5cf6',
  checkout_abandonment: '#22d3ee',
  subscription_failure: '#fbbf24',
  mandate_failure: '#60a5fa',
  receivable_delay: '#f472b6',
  default: '#a78bfa',
}

const paymentPalette: Record<string, string> = {
  UPI: '#8b5cf6',
  CARD: '#22d3ee',
  NETBANKING: '#60a5fa',
  WALLET: '#a78bfa',
  EMI: '#fbbf24',
  default: '#64748b',
}

export default function Home() {
  const [dashboard, setDashboard] = useState<DashboardData | null>(null)
  const [eventMix, setEventMix] = useState<EventMixData | null>(null)
  const [paymentMethods, setPaymentMethods] = useState<PaymentMethodsData | null>(null)
  const [signals, setSignals] = useState<SignalsData | null>(null)
  const [loadingState, setLoadingState] = useState<LoadingState>('loading')
  const [error, setError] = useState<string | null>(null)
  const [allocation, setAllocation] = useState(300)
  const [selectedEventType, setSelectedEventType] = useState<string | null>(null)
  const [selectedPayment, setSelectedPayment] = useState<string | null>(null)

  const API_URL = process.env.NEXT_PUBLIC_API_URL || ''

  useEffect(() => {
    const fetchData = async () => {
      try {
        setError(null)

        if (!API_URL) {
          throw new Error('NEXT_PUBLIC_API_URL is not configured for this deployment.')
        }

        const [dashboardRes, eventMixRes, paymentMethodsRes, signalsRes] = await Promise.all([
          fetch(`${API_URL}/api/dashboard`, { cache: 'no-store' }),
          fetch(`${API_URL}/api/dashboard/event-mix`, { cache: 'no-store' }),
          fetch(`${API_URL}/api/dashboard/payment-methods`, { cache: 'no-store' }),
          fetch(`${API_URL}/api/dashboard/signals`, { cache: 'no-store' }),
        ])

        if (!dashboardRes.ok) throw new Error('Dashboard endpoint failed')
        if (!eventMixRes.ok) throw new Error('Event mix endpoint failed')
        if (!paymentMethodsRes.ok) throw new Error('Payment methods endpoint failed')
        if (!signalsRes.ok) throw new Error('Signals endpoint failed')

        setDashboard(await dashboardRes.json())
        setEventMix(await eventMixRes.json())
        setPaymentMethods(await paymentMethodsRes.json())
        setSignals(await signalsRes.json())
        setLoadingState('success')
      } catch (err) {
        console.error('Dashboard fetch failed', err)
        setError(err instanceof Error ? err.message : 'Recovery data could not be loaded.')
        setLoadingState('error')
      }
    }

    fetchData()
    const interval = setInterval(fetchData, 10000)
    return () => clearInterval(interval)
  }, [API_URL])

  const eventEntries = useMemo(() => {
    return Object.entries(eventMix || {}).sort((a, b) => b[1].exposure_minor - a[1].exposure_minor)
  }, [eventMix])

  const paymentEntries = useMemo(() => {
    return Object.entries(paymentMethods || {}).sort((a, b) => b[1].exposure_minor - a[1].exposure_minor)
  }, [paymentMethods])

  const totalRiskExposure = dashboard?.risk_exposure_minor ?? 0
  const totalEventExposure = eventEntries.reduce((total, [, row]) => total + row.exposure_minor, 0)
  const totalPaymentExposure = paymentEntries.reduce((total, [, row]) => total + row.exposure_minor, 0)
  const eventCoverage = dashboard?.recovery_eligible ? (dashboard.recovery_eligible / Math.max(dashboard.live_events, 1)) * 100 : 0

  const formatCurrency = (minor: number) => `₹${(minor / 100).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
  const formatMoneyShort = (minor: number) => {
    const rupees = minor / 100
    if (rupees >= 100000) {
      return `₹${(rupees / 100000).toFixed(1)}L`
    }
    if (rupees >= 1000) {
      return `₹${(rupees / 1000).toFixed(1)}K`
    }
    return `₹${rupees.toLocaleString('en-IN')}`
  }
  const formatCompact = (value: number) => value.toLocaleString('en-IN')

  const activeEvent = selectedEventType ? eventMix?.[selectedEventType] : eventEntries[0]?.[1]
  const activePayment = selectedPayment ? paymentMethods?.[selectedPayment] : paymentEntries[0]?.[1]

  const paymentMap = paymentEntries.reduce((acc, [method, row]) => {
    acc[method] = row.exposure_minor
    return acc
  }, {} as Record<string, number>)

  const totalCircle = paymentEntries.reduce((sum, [, row]) => sum + row.exposure_minor, 0)
  const paymentSegments = paymentEntries.map(([method, row]) => {
    const share = totalCircle ? (row.exposure_minor / totalCircle) * 100 : 0
    return {
      method,
      share,
      amount: row.exposure_minor,
      color: paymentPalette[method] || paymentPalette.default,
    }
  })

  const paymentGradient = paymentSegments.length
    ? paymentSegments
        .map((segment, index) => {
          const start = paymentSegments.slice(0, index).reduce((sum, item) => sum + item.share, 0)
          const end = start + segment.share
          return `${segment.color} ${start}% ${end}%`
        })
        .join(', ')
    : '#8b5cf6 0% 100%'

  const allocationCoverage = (allocation / 1000) * 100

  const loadingCard = (
    <div className="panel loading-panel">
      <div className="skeleton short" />
      <div className="skeleton medium" />
      <div className="skeleton long" />
    </div>
  )

  if (loadingState === 'loading') {
    return (
      <main className="shell-shell">
        <div className="shell">
          <aside className="sidebar">
            <div className="brand-block">
              <div className="brand-mark">V</div>
              <div>
                <p className="brand-name">VEYRO</p>
                <p className="brand-subtitle">AI Revenue Recovery Intelligence</p>
              </div>
            </div>
            <nav className="nav">
              {['Overview', 'Recovery Map', 'Signals', 'Allocation', 'Audit'].map((item) => (
                <button key={item} className="nav-item muted" type="button">
                  {item}
                </button>
              ))}
            </nav>
          </aside>

          <div className="workspace">
            <header className="topbar">
              <div className="topbar-title">Live pipeline</div>
              <div className="topbar-meta">
                <span className="live-pill"><span className="pulse" /> Live</span>
                <span>Updated just now</span>
              </div>
            </header>
            <div className="content-stack">
              <section className="hero panel">{loadingCard}</section>
            </div>
          </div>
        </div>
      </main>
    )
  }

  if (loadingState === 'error') {
    return (
      <main className="shell-shell">
        <div className="shell center-shell">
          <div className="panel error-panel">
            <p className="eyebrow">Recovery data unavailable</p>
            <h1>Recovery data couldn't be loaded.</h1>
            <p>{error}</p>
            <button
              type="button"
              className="primary-button"
              onClick={() => window.location.reload()}
            >
              Try again
            </button>
          </div>
        </div>
      </main>
    )
  }

  return (
    <main className="shell-shell">
      <div className="shell">
        <aside className="sidebar">
          <div className="brand-block">
            <div className="brand-mark">V</div>
            <div>
              <p className="brand-name">VEYRO</p>
              <p className="brand-subtitle">AI Revenue Recovery Intelligence</p>
            </div>
          </div>

          <nav className="nav" aria-label="Main navigation">
            {['Overview', 'Recovery Map', 'Signals', 'Allocation', 'Audit'].map((item, idx) => (
              <button
                key={item}
                type="button"
                className={`nav-item ${idx === 0 ? 'active' : 'muted'}`}
              >
                {item}
              </button>
            ))}
          </nav>

          <div className="sidebar-card">
            <p className="eyebrow subtle">Portfolio health</p>
            <div className="big-number">{formatMoneyShort(totalRiskExposure)}</div>
            <p className="micro-label">risk exposure in motion</p>
          </div>
        </aside>

        <div className="workspace">
          <header className="topbar">
            <div className="brand-inline">VEYRO</div>
            <div className="topbar-meta">
              <span className="live-pill"><span className="pulse" /> Live pipeline</span>
              <span>Updated {new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
            </div>
          </header>

          <div className="content-stack">
            <section className="hero panel">
              <div className="hero-copy">
                <p className="eyebrow">Revenue at risk</p>
                <h1>{formatMoneyShort(totalRiskExposure)}</h1>
                <p className="hero-subtitle">Across the active recovery portfolio</p>

                <div className="hero-stats">
                  <div>
                    <span className="meta-label">Live events</span>
                    <strong>{formatCompact(dashboard?.live_events ?? 0)}</strong>
                  </div>
                  <div>
                    <span className="meta-label">Recovery eligible</span>
                    <strong>{formatCompact(dashboard?.recovery_eligible ?? 0)}</strong>
                  </div>
                  <div>
                    <span className="meta-label">Avg. exposure</span>
                    <strong>{formatMoneyShort((dashboard?.risk_exposure_minor ?? 0) / Math.max(dashboard?.live_events ?? 1, 1))}</strong>
                  </div>
                </div>

                <div className="cta-row">
                  <a href="#map" className="primary-button">Explore recovery opportunities →</a>
                  <button type="button" className="secondary-button">View signals</button>
                </div>
              </div>

              <div className="hero-visual">
                <div className="orb-wrap">
                  <div
                    className="allocation-orb"
                    style={{
                      background: `conic-gradient(#8b5cf6 0 38%, #22d3ee 38% 72%, #fbbf24 72% 100%)`,
                    }}
                  >
                    <div className="orb-center">
                      <strong>{allocation}</strong>
                      <span>actions</span>
                    </div>
                  </div>
                </div>
                <div className="orb-metric">
                  <span className="eyebrow subtle">Allocation preview</span>
                  <strong>{allocationCoverage.toFixed(1)}%</strong>
                  <span>of eligible portfolio</span>
                </div>
              </div>
            </section>

            <section className="metrics-grid">
              <div className="metric-card panel">
                <span className="meta-label">Revenue events</span>
                <strong>{formatCompact(dashboard?.live_events ?? 0)}</strong>
              </div>
              <div className="metric-card panel">
                <span className="meta-label">Recovery eligible</span>
                <strong>{formatCompact(dashboard?.recovery_eligible ?? 0)}</strong>
              </div>
              <div className="metric-card panel">
                <span className="meta-label">Average exposure</span>
                <strong>{formatMoneyShort((dashboard?.risk_exposure_minor ?? 0) / Math.max(dashboard?.recovery_eligible ?? 1, 1))}</strong>
              </div>
            </section>

            <section id="map" className="panel map-panel">
              <div className="section-header">
                <div>
                  <p className="eyebrow">Recovery map</p>
                  <h2>Where revenue is slipping</h2>
                </div>
                <span className="section-tag">{eventEntries.length || 0} active event streams</span>
              </div>

              <div className="map-rows">
                {eventEntries.map(([type, row]) => {
                  const percent = totalEventExposure ? (row.exposure_minor / totalEventExposure) * 100 : 0
                  const isActive = selectedEventType === type || (!selectedEventType && type === eventEntries[0]?.[0])
                  return (
                    <button
                      type="button"
                      key={type}
                      className={`map-row ${isActive ? 'active' : ''}`}
                      onClick={() => setSelectedEventType(type)}
                    >
                      <div className="row-head">
                        <span className="title-group">
                          <span className="dot" style={{ background: eventPalette[type] || eventPalette.default }} />
                          {type.replace(/_/g, ' ')}
                        </span>
                        <span className="amount">{formatMoneyShort(row.exposure_minor)}</span>
                      </div>
                      <div className="bar-shell">
                        <span className="bar-fill" style={{ width: `${percent}%`, background: eventPalette[type] || eventPalette.default }} />
                      </div>
                      <div className="row-meta">
                        <span>{row.count.toLocaleString('en-IN')} events</span>
                        <span>{percent.toFixed(1)}% of total risk</span>
                      </div>
                    </button>
                  )
                })}
              </div>
            </section>

            <section className="two-panel-grid">
              <div className="panel payment-panel">
                <div className="section-header compact">
                  <div>
                    <p className="eyebrow">Payment pressure</p>
                    <h2>At-risk payment flow</h2>
                  </div>
                </div>

                <div className="payment-layout">
                  <div className="donut-wrap">
                    <div
                      className="donut"
                      style={{ background: `conic-gradient(${paymentGradient})` }}
                    >
                      <div className="donut-inner">
                        <strong>{formatMoneyShort(totalPaymentExposure)}</strong>
                        <span>at risk</span>
                      </div>
                    </div>
                  </div>

                  <div className="payment-list">
                    {paymentEntries.map(([method, row]) => {
                      const percent = totalPaymentExposure ? (row.exposure_minor / totalPaymentExposure) * 100 : 0
                      const isActive = selectedPayment === method || (!selectedPayment && method === paymentEntries[0]?.[0])
                      return (
                        <button
                          type="button"
                          key={method}
                          className={`payment-item ${isActive ? 'active' : ''}`}
                          onClick={() => setSelectedPayment(method)}
                        >
                          <div className="method-row">
                            <span className="title-group">
                              <span className="dot" style={{ background: paymentPalette[method] || paymentPalette.default }} />
                              {method}
                            </span>
                            <strong>{percent.toFixed(1)}%</strong>
                          </div>
                          <div className="amount-line">{formatMoneyShort(row.exposure_minor)}</div>
                        </button>
                      )
                    })}
                  </div>
                </div>
              </div>

              <div className="panel signals-panel">
                <div className="section-header compact">
                  <div>
                    <p className="eyebrow">Signals</p>
                    <h2>What needs attention first</h2>
                  </div>
                </div>

                <div className="signal-grid">
                  <div className="signal-card violet">
                    <span className="signal-tag">High-value cases</span>
                    <strong>{formatCompact(signals?.high_value_events ?? 0)}</strong>
                    <p>Accounts with material exposure requiring stronger review.</p>
                  </div>

                  <div className="signal-card cyan">
                    <span className="signal-tag">Low-value friction</span>
                    <strong>{formatCompact(signals?.low_value_friction ?? 0)}</strong>
                    <p>Cases that can consume recovery capacity without strong yield.</p>
                  </div>

                  <div className="signal-card amber">
                    <span className="signal-tag">Fatigued accounts</span>
                    <strong>{formatCompact(signals?.fatigued_accounts ?? 0)}</strong>
                    <p>Customers already contacted repeatedly across prior actions.</p>
                  </div>
                </div>
              </div>
            </section>

            <section className="panel simulator-panel">
              <div className="section-header compact">
                <div>
                  <p className="eyebrow">Allocation</p>
                  <h2>How much recovery capacity should I deploy?</h2>
                </div>
              </div>

              <div className="simulator-layout">
                <div className="simulator-controls">
                  <label className="control-group">
                    <span>Actions available</span>
                    <div className="range-shell">
                      <input
                        type="range"
                        min={50}
                        max={1000}
                        value={allocation}
                        onChange={(event) => setAllocation(Number(event.target.value))}
                      />
                    </div>
                    <strong>{allocation}</strong>
                  </label>

                  <div className="mini-stats">
                    <div>
                      <span>Coverage</span>
                      <strong>{allocationCoverage.toFixed(1)}%</strong>
                    </div>
                    <div>
                      <span>Portfolio reach</span>
                      <strong>{formatCompact(Math.max(0, dashboard?.recovery_eligible ?? 0 - allocation))}</strong>
                    </div>
                  </div>
                </div>

                <div className="simulator-visual">
                  <div className="simulator-figure">
                    <span>Current capacity</span>
                    <strong>{allocation}</strong>
                    <small>actions</small>
                  </div>
                  <div className="simulator-note">
                    <span>Estimated portfolio coverage</span>
                    <strong>{allocationCoverage.toFixed(1)}%</strong>
                  </div>
                </div>
              </div>
            </section>

            <section className="panel flow-panel">
              <div className="section-header compact">
                <div>
                  <p className="eyebrow">Recovery command flow</p>
                  <h2>From signal to action</h2>
                </div>
              </div>

              <div className="flow-grid">
                {['Detect', 'Understand', 'Prioritize', 'Act', 'Measure'].map((step, idx) => (
                  <div key={step} className="flow-step">
                    <span className="step-index">0{idx + 1}</span>
                    <strong>{step}</strong>
                    <p>
                      {idx === 0 && 'Revenue events, risk exposure, and event mix'}
                      {idx === 1 && 'Payment-method leverage, fatigue, and high-value cases'}
                      {idx === 2 && 'Recovery capacity, coverage, and prioritization logic'}
                      {idx === 3 && 'Guardrails and intervention timing for recovery actions'}
                      {idx === 4 && 'Measured lift versus the active recovery portfolio'}
                    </p>
                  </div>
                ))}
              </div>
            </section>

            <section className="panel principles-panel">
              <div className="section-header compact">
                <div>
                  <p className="eyebrow">Why VEYRO</p>
                  <h2>Recovery with precision, not noise</h2>
                </div>
              </div>

              <div className="principles-grid">
                {[
                  'Don’t recover everything. Recover what matters.',
                  'Don’t let AI run unchecked. Guard every action.',
                  'Don’t claim every payment as a win. Measure incrementality.',
                ].map((item, idx) => (
                  <div key={item} className="principle-card">
                    <span>0{idx + 1}</span>
                    <p>{item}</p>
                  </div>
                ))}
              </div>
            </section>
          </div>
        </div>
      </div>
    </main>
  )
}
