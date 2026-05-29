'use client'

import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface Message {
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: Date
}

const REGIONS = ['APJ', 'MEE', 'EMEA', 'GC', 'LAC', 'NA'] as const
const CROSS_REGIONS = ['MEE', 'EMEA', 'NA', 'LAC'] as const

const REGION_COLORS: Record<string, string> = {
  APJ: '#1565C0',
  MEE: '#1976D2',
  EMEA: '#1E88E5',
  GC: '#1A237E',
  LAC: '#7B1FA2',
  NA: '#00897B',
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([{
    role: 'assistant',
    content: 'Welcome to the Onboarding Assignment Agent. Upload your consultant data file to get started, then ask me about capacity, consultant scores, or run an assignment optimization.',
    timestamp: new Date(),
  }])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [dataLoaded, setDataLoaded] = useState(false)
  const [dataInfo, setDataInfo] = useState<any>(null)
  const [customerJson, setCustomerJson] = useState('{}')
  const [crossPcts, setCrossPcts] = useState<Record<string, number>>({ MEE: 0, EMEA: 0, NA: 0, LAC: 0 })
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [showCustomerModal, setShowCustomerModal] = useState(false)
  const [regionInputs, setRegionInputs] = useState<Record<string, string>>({ APJ: '', MEE: '', EMEA: '', GC: '', LAC: '', NA: '' })
  const [modalCrossPcts, setModalCrossPcts] = useState<Record<string, number>>({ MEE: 0, EMEA: 0, NA: 0, LAC: 0 })
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async () => {
    if (!input.trim() || isLoading) return
    const userMessage: Message = { role: 'user', content: input.trim(), timestamp: new Date() }
    setMessages((prev) => [...prev, userMessage])
    setInput('')
    setIsLoading(true)
    try {
      const history = messages.slice(-8).map((m) => ({ role: m.role, content: m.content }))
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userMessage.content, customer_data: customerJson, cross_region_pcts: crossPcts, history }),
      })
      const data = await res.json()
      setMessages((prev) => [...prev, { role: 'assistant', content: data.response || data.detail || 'No response.', timestamp: new Date() }])
    } catch (err: any) {
      setMessages((prev) => [...prev, { role: 'assistant', content: `Connection error: ${err.message}.`, timestamp: new Date() }])
    } finally {
      setIsLoading(false)
    }
  }

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setIsLoading(true)
    setMessages((prev) => [...prev, { role: 'system', content: `Uploading ${file.name}...`, timestamp: new Date() }])
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await fetch('/api/upload', { method: 'POST', body: formData })
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || 'Upload failed') }
      const data = await res.json()
      setDataLoaded(true)
      setDataInfo(data)
      setMessages((prev) => [...prev, {
        role: 'assistant',
        content: `Data loaded successfully from **${data.file_name}**.\n\n- **${data.row_count}** consultants processed\n- **${data.active_count}** available (Active + Willing)\n- **${data.total_capacity}** total customer slots\n\nYou can now ask about capacity, scores, individual consultants, or run an assignment.`,
        timestamp: new Date(),
      }])
    } catch (err: any) {
      setMessages((prev) => [...prev, { role: 'assistant', content: `Upload failed: ${err.message}`, timestamp: new Date() }])
    } finally {
      setIsLoading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const openCustomerModal = () => {
    // Pre-populate modal from existing customerJson
    try {
      const parsed = JSON.parse(customerJson)
      const inputs: Record<string, string> = { APJ: '', MEE: '', EMEA: '', GC: '', LAC: '', NA: '' }
      for (const r of REGIONS) { inputs[r] = (parsed[r] || []).join('\n') }
      setRegionInputs(inputs)
    } catch { /* keep existing */ }
    setModalCrossPcts({ ...crossPcts })
    setShowCustomerModal(true)
  }

  const handleApply = () => {
    const parsed: Record<string, string[]> = {}
    for (const r of REGIONS) {
      const ids = regionInputs[r].split(/[\n,]+/).map(s => s.trim()).filter(Boolean)
      parsed[r] = ids
    }
    setCustomerJson(JSON.stringify(parsed))
    setCrossPcts({ ...modalCrossPcts })
    setShowCustomerModal(false)
  }

  const totalCustomers = (() => {
    try { return Object.values(JSON.parse(customerJson)).reduce((s: number, v: any) => s + v.length, 0) as number }
    catch { return 0 }
  })()

  const formatTime = (date: Date) => date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

  return (
    <div className="flex h-screen bg-white">

      {/* ── Customer Data Modal ────────────────────────────────────── */}
      {showCustomerModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-5xl max-h-[90vh] overflow-y-auto">
            {/* Modal header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
              <div>
                <h2 className="text-lg font-bold text-gray-800">Customer IDs by Region</h2>
                <p className="text-xs text-gray-500 mt-0.5">Enter customer IDs per region. MEE, EMEA, NA and LAC can redirect a % of customers to APJ.</p>
              </div>
              <button onClick={() => setShowCustomerModal(false)} className="text-gray-400 hover:text-gray-600 transition-colors">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>

            {/* Region grid */}
            <div className="p-6 grid grid-cols-3 gap-4">
              {REGIONS.map((region) => {
                const hasCross = (CROSS_REGIONS as readonly string[]).includes(region)
                const pct = modalCrossPcts[region] ?? 0
                return (
                  <div key={region} className="rounded-xl overflow-hidden border border-gray-200 shadow-sm flex flex-col">
                    {/* Card header */}
                    <div className="px-4 py-2.5 text-white font-bold text-sm" style={{ backgroundColor: REGION_COLORS[region] }}>
                      {region}
                    </div>
                    {/* Textarea */}
                    <div className="flex-1 p-3 bg-gray-50">
                      <textarea
                        value={regionInputs[region]}
                        onChange={(e) => setRegionInputs(prev => ({ ...prev, [region]: e.target.value }))}
                        rows={5}
                        className="w-full text-xs text-gray-600 bg-white border border-gray-200 rounded-lg p-2.5 resize-none focus:outline-none focus:border-blue-400 font-mono"
                        placeholder={`Enter ${region} customer IDs\none per line or comma-separated\ne.g. CUST-001\n\nClients here are assigned only\nto ${region} consultants.`}
                      />
                    </div>
                    {/* Slider (cross-region only) */}
                    {hasCross && (
                      <div className="px-3 pb-3 bg-gray-50 border-t border-gray-100">
                        <div className="flex items-center justify-between mb-1 mt-2">
                          <span className="text-[10px] text-gray-500 font-medium">% redirected to APJ</span>
                          <span className="text-xs font-bold text-red-500">{pct}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <div className="w-2 h-2 rounded-full bg-red-500 shrink-0" />
                          <input
                            type="range"
                            min={0}
                            max={100}
                            value={pct}
                            onChange={(e) => setModalCrossPcts(prev => ({ ...prev, [region]: Number(e.target.value) }))}
                            className="flex-1 h-1.5 accent-red-500"
                          />
                          <input
                            type="number"
                            min={0}
                            max={100}
                            value={pct}
                            onChange={(e) => setModalCrossPcts(prev => ({ ...prev, [region]: Math.min(100, Math.max(0, Number(e.target.value))) }))}
                            className="w-12 text-xs text-center border border-gray-200 rounded px-1 py-0.5 bg-white"
                          />
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>

            {/* Modal footer */}
            <div className="flex items-center justify-between px-6 py-4 border-t border-gray-200 bg-gray-50 rounded-b-2xl">
              <span className="text-xs text-gray-500">
                {Object.values(regionInputs).reduce((s, v) => s + v.split(/[\n,]+/).filter(x => x.trim()).length, 0)} customers entered
              </span>
              <div className="flex gap-3">
                <button onClick={() => setShowCustomerModal(false)} className="px-4 py-2 text-sm text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-100 transition-colors">
                  Cancel
                </button>
                <button onClick={handleApply} className="px-4 py-2 text-sm text-white rounded-lg transition-colors font-medium" style={{ backgroundColor: '#1565C0' }}>
                  Apply
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Sidebar ────────────────────────────────────────────────── */}
      <div className={`${sidebarOpen ? 'w-72' : 'w-0'} transition-all duration-200 border-r border-sap-gray-200 bg-sap-gray-100 flex flex-col overflow-hidden shrink-0`}>
        <div className="p-4 border-b border-sap-gray-200">
          <h2 className="text-sm font-bold text-sap-gray-600 uppercase tracking-wider">Onboarding Assignment Agent</h2>
        </div>

        {/* File Upload */}
        <div className="p-4 border-b border-sap-gray-200">
          <label className="text-xs font-semibold text-sap-gray-500 uppercase tracking-wider mb-2 block">Consultant Data</label>
          <input type="file" ref={fileInputRef} onChange={handleFileUpload} accept=".xlsx,.xls,.csv" className="hidden" />
          <button onClick={() => fileInputRef.current?.click()} className="w-full px-3 py-2.5 bg-white border border-sap-gray-300 rounded-lg text-sm text-sap-gray-600 hover:border-sap-blue hover:text-sap-blue transition-colors flex items-center justify-center gap-2">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" /></svg>
            Upload Excel/CSV
          </button>
          {dataInfo && (
            <div className="mt-2 p-2 bg-white rounded border border-sap-gray-200 text-xs text-sap-gray-500">
              <div className="flex justify-between"><span>File:</span><span className="font-medium text-sap-gray-600 truncate ml-2">{dataInfo.file_name}</span></div>
              <div className="flex justify-between mt-1"><span>Consultants:</span><span className="font-medium text-sap-gray-600">{dataInfo.row_count}</span></div>
              <div className="flex justify-between mt-1"><span>Available:</span><span className="font-medium text-green-600">{dataInfo.active_count}</span></div>
              <div className="flex justify-between mt-1"><span>Capacity:</span><span className="font-medium text-sap-blue">{dataInfo.total_capacity} slots</span></div>
            </div>
          )}
        </div>

        {/* Quick Actions */}
        <div className="p-4 flex-1">
          <label className="text-xs font-semibold text-sap-gray-500 uppercase tracking-wider mb-2 block">Quick Actions</label>
          <div className="space-y-1.5">
            {/* Enter Customer Data button — highlighted */}
            <button
              onClick={openCustomerModal}
              className="w-full text-left px-3 py-2 text-xs rounded-md transition-colors border flex items-center justify-between gap-2 font-medium text-white"
              style={{ backgroundColor: '#1565C0', borderColor: '#1565C0' }}
            >
              <span className="flex items-center gap-1.5">
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
                Enter Customer Data
              </span>
              {totalCustomers > 0 && (
                <span className="bg-white/20 text-white text-[10px] px-1.5 py-0.5 rounded-full font-bold">{totalCustomers}</span>
              )}
            </button>

            {[
              { label: 'Show capacity', cmd: 'Show regional capacity overview' },
              { label: 'Top performers', cmd: 'Show top 10 consultants' },
              { label: 'Scoring method', cmd: 'How are consultants scored?' },
              { label: 'Run assignment', cmd: 'Run assignment optimization' },
            ].map((action) => (
              <button key={action.cmd} onClick={() => setInput(action.cmd)} className="w-full text-left px-3 py-2 text-xs text-sap-gray-600 hover:bg-white hover:text-sap-blue rounded-md transition-colors border border-transparent hover:border-sap-gray-200">
                {action.label}
              </button>
            ))}
          </div>

          {/* Cross-region summary if any pcts set */}
          {Object.values(crossPcts).some(v => v > 0) && (
            <div className="mt-4 p-2 bg-white rounded border border-sap-gray-200 text-[10px] text-sap-gray-500">
              <p className="font-semibold text-sap-gray-600 mb-1">Cross-region (→ APJ)</p>
              {CROSS_REGIONS.filter(r => crossPcts[r] > 0).map(r => (
                <div key={r} className="flex justify-between"><span>{r}:</span><span className="font-medium text-red-500">{crossPcts[r]}%</span></div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── Main Chat Area ─────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header className="h-14 border-b border-sap-gray-200 bg-white flex items-center px-4 gap-3 shrink-0">
          <button onClick={() => setSidebarOpen(!sidebarOpen)} className="p-1.5 rounded-md hover:bg-sap-gray-100 text-sap-gray-500 transition-colors">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" /></svg>
          </button>
          <div className="w-px h-6 bg-sap-gray-200" />
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded bg-sap-blue flex items-center justify-center">
              <span className="text-white text-xs font-bold">OA</span>
            </div>
            <div>
              <h1 className="text-sm font-semibold text-sap-gray-600 leading-tight">Onboarding Assignment Agent</h1>
              <p className="text-[10px] text-sap-gray-400">AI Driven Optimization Engine</p>
            </div>
          </div>
          <div className="ml-auto flex items-center gap-2">
            {dataLoaded && <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-green-50 text-green-700 border border-green-200">Data Loaded</span>}
            {totalCustomers > 0 && <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-orange-50 text-orange-700 border border-orange-200">{totalCustomers} Customers</span>}
            <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-sap-blue-light text-sap-blue border border-blue-200">v1.0</span>
          </div>
        </header>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-6">
          <div className="max-w-full mx-auto space-y-4 px-2">
            {messages.map((msg, i) => (
              <div key={i} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : ''}`}>
                {msg.role !== 'user' && (
                  <div className="w-7 h-7 rounded bg-sap-blue flex items-center justify-center shrink-0 mt-0.5">
                    <span className="text-white text-[10px] font-bold">AI</span>
                  </div>
                )}
                <div className={`min-w-0 flex-1 max-w-[95%] rounded-xl px-4 py-3 text-sm leading-relaxed ${msg.role === 'user' ? 'bg-sap-blue text-white' : msg.role === 'system' ? 'bg-sap-gray-100 text-sap-gray-500 text-xs italic' : 'bg-sap-gray-100 text-sap-gray-600'}`}>
                  {msg.role === 'assistant' ? (
                    <div className="chat-content overflow-x-auto">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                    </div>
                  ) : <p>{msg.content}</p>}
                  <span className={`block mt-1.5 text-[10px] ${msg.role === 'user' ? 'text-blue-200' : 'text-sap-gray-400'}`}>{formatTime(msg.timestamp)}</span>
                </div>
                {msg.role === 'user' && (
                  <div className="w-7 h-7 rounded bg-sap-navy flex items-center justify-center shrink-0 mt-0.5">
                    <span className="text-white text-[10px] font-bold">U</span>
                  </div>
                )}
              </div>
            ))}
            {isLoading && (
              <div className="flex gap-3">
                <div className="w-7 h-7 rounded bg-sap-blue flex items-center justify-center shrink-0">
                  <span className="text-white text-[10px] font-bold">AI</span>
                </div>
                <div className="bg-sap-gray-100 rounded-xl px-4 py-3">
                  <div className="flex gap-1.5">
                    <div className="w-2 h-2 rounded-full bg-sap-gray-400 animate-bounce" style={{ animationDelay: '0ms' }} />
                    <div className="w-2 h-2 rounded-full bg-sap-gray-400 animate-bounce" style={{ animationDelay: '150ms' }} />
                    <div className="w-2 h-2 rounded-full bg-sap-gray-400 animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input */}
        <div className="border-t border-sap-gray-200 bg-white p-4 shrink-0">
          <div className="max-w-full mx-auto">
            <div className="flex gap-2">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
                placeholder={dataLoaded ? 'Ask about capacity, consultants, or type "assign" to run...' : 'Upload data to get started, or ask a general question...'}
                className="flex-1 px-4 py-2.5 border border-sap-gray-300 rounded-xl text-sm text-sap-gray-600 placeholder-sap-gray-400 focus:outline-none focus:border-sap-blue focus:ring-1 focus:ring-sap-blue/20"
                disabled={isLoading}
              />
              <button
                onClick={handleSend}
                disabled={isLoading || !input.trim()}
                className="px-4 py-2.5 bg-sap-blue text-white rounded-xl text-sm font-medium hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-1.5"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" /></svg>
                Send
              </button>
            </div>
            <p className="mt-2 text-center text-[10px] text-sap-gray-400">Powered by AI Driven optimization with SAP AI Core LLM</p>
          </div>
        </div>
      </div>
    </div>
  )
}
