import {
  AlertTriangle,
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  CircleHelp,
  ClipboardCheck,
  CloudUpload,
  Download,
  FileCheck2,
  FileImage,
  FileJson,
  FileText,
  Info,
  Loader2,
  LockKeyhole,
  Maximize2,
  Minus,
  PanelRight,
  Plus,
  Printer,
  RotateCcw,
  ScanSearch,
  Shield,
  ShieldCheck,
  Trash2,
  UploadCloud,
  WandSparkles,
  X,
} from 'lucide-react'
import {
  type PointerEvent as ReactPointerEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react'
import { api, ApiError } from './lib/api'
import { PURPOSE_PRESETS, presetDecision, presetMaskLastN, type PurposePreset } from './config/presets'
import {
  confidencePercent,
  confidenceTone,
  downloadBlob,
  downloadJson,
  formatBytes,
  humanizeKind,
} from './lib/format'
import type {
  DocumentType,
  FindingResponse,
  ReportResponse,
  UploadResponse,
  VerificationResponse,
} from './types/api'

const MAX_FILE_BYTES = 10 * 1024 * 1024
const ACCEPTED_TYPES = ['application/pdf', 'image/jpeg', 'image/png']
const ACCEPTED_EXTENSIONS = '.pdf,.jpg,.jpeg,.png'
const FALLBACK_PAGE_SIZE = { width: 612, height: 792 }

type WorkflowStep = 'upload' | 'review' | 'preview' | 'export'
type BusyState = 'health' | 'upload' | 'analyze' | 'export' | 'delete' | null
type Decision = 'redact' | 'keep'
type Point = { x: number; y: number }
type Bbox = [number, number, number, number]

interface ReviewedFinding extends FindingResponse {
  decision: Decision
  manual?: boolean
  keepLastN?: number
}

interface PreviewAsset {
  objectUrl: string
  pageUrl: (page: number) => string
}

const STEPS: { id: WorkflowStep; label: string; helper: string }[] = [
  { id: 'upload', label: 'Upload', helper: 'Add a document' },
  { id: 'review', label: 'Review', helper: 'Check detections' },
  { id: 'preview', label: 'Preview', helper: 'Inspect redactions' },
  { id: 'export', label: 'Export', helper: 'Download safely' },
]

function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.detail
  if (error instanceof Error) return error.message
  return 'Something went wrong. Please try again.'
}

function createPreviewAsset(file: File): PreviewAsset {
  const objectUrl = URL.createObjectURL(file)
  return {
    objectUrl,
    pageUrl: (page) => (file.type === 'application/pdf' ? `${objectUrl}#page=${page}&view=FitH` : objectUrl),
  }
}

function normalizedBbox(bbox: Bbox, pageSize: { width: number; height: number }): Bbox {
  const [x0, y0, x1, y1] = bbox
  return [
    Math.max(0, Math.min(pageSize.width, x0)),
    Math.max(0, Math.min(pageSize.height, y0)),
    Math.max(0, Math.min(pageSize.width, x1)),
    Math.max(0, Math.min(pageSize.height, y1)),
  ]
}

function makeFindingId(): string {
  return `manual-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

function App() {
  const [busy, setBusy] = useState<BusyState>('health')
  const [apiOnline, setApiOnline] = useState<boolean | null>(null)
  const [apiMessage, setApiMessage] = useState('Checking API connection…')
  const [workflowStep, setWorkflowStep] = useState<WorkflowStep>('upload')
  const [file, setFile] = useState<File | null>(null)
  const [previewAsset, setPreviewAsset] = useState<PreviewAsset | null>(null)
  const [upload, setUpload] = useState<UploadResponse | null>(null)
  const [report, setReport] = useState<ReportResponse | null>(null)
  const [findings, setFindings] = useState<ReviewedFinding[]>([])
  const [selectedFindingId, setSelectedFindingId] = useState<string | null>(null)
  const [selectedPage, setSelectedPage] = useState(1)
  const [imageSize, setImageSize] = useState<{ width: number; height: number } | null>(null)
  const [purposeId, setPurposeId] = useState('identity')
  const [useOcr, setUseOcr] = useState(true)
  const [flattenToImage, setFlattenToImage] = useState(false)
  const [keepLastN, setKeepLastN] = useState<number | null>(null)
  const [manualMode, setManualMode] = useState(false)
  const [exported, setExported] = useState<{ blob: Blob; filename: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [fileError, setFileError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const purpose = PURPOSE_PRESETS.find((preset) => preset.id === purposeId) || PURPOSE_PRESETS[0]
  const sessionId = upload?.session_id || null
  const pageCount = report?.pages || upload?.pages || 1
  const currentPageFindings = findings.filter((finding) => finding.page === selectedPage)
  const redactedCount = findings.filter((finding) => finding.decision === 'redact').length
  const stepIndex = STEPS.findIndex((step) => step.id === workflowStep)

  useEffect(() => {
    let active = true
    api.health()
      .then((health) => {
        if (!active) return
        setApiOnline(health.status === 'ok')
        setApiMessage(health.storage === 'ready' ? 'API online · temporary storage ready' : 'API online')
      })
      .catch((healthError: unknown) => {
        if (!active) return
        setApiOnline(false)
        setApiMessage(getErrorMessage(healthError))
      })
      .finally(() => {
        if (active) setBusy(null)
      })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    return () => {
      if (previewAsset) URL.revokeObjectURL(previewAsset.objectUrl)
    }
  }, [previewAsset])

  const clearFeedback = useCallback(() => {
    setError(null)
    setNotice(null)
  }, [])

  const acceptFile = useCallback((candidate: File | undefined) => {
    if (!candidate) return
    clearFeedback()
    setFileError(null)
    if (!ACCEPTED_TYPES.includes(candidate.type)) {
      setFileError('Choose a PDF, JPG, or PNG file.')
      return
    }
    if (candidate.size > MAX_FILE_BYTES) {
      setFileError('That file is larger than 10 MB. Choose a smaller document.')
      return
    }
    if (previewAsset) URL.revokeObjectURL(previewAsset.objectUrl)
    setFile(candidate)
    setPreviewAsset(createPreviewAsset(candidate))
    setUpload(null)
    setReport(null)
    setFindings([])
    setExported(null)
    setSelectedPage(1)
    setImageSize(null)
    setFlattenToImage(false)
    setWorkflowStep('upload')
    setManualMode(false)
  }, [clearFeedback, previewAsset])

  const handleUpload = async () => {
    if (!file) return
    clearFeedback()
    setBusy('upload')
    try {
      const result = await api.upload(file)
      setUpload(result)
      setNotice(`${file.name} is ready for analysis.`)
    } catch (uploadError) {
      setError(getErrorMessage(uploadError))
    } finally {
      setBusy(null)
    }
  }

  const handleAnalyze = async () => {
    if (!sessionId) return
    clearFeedback()
    setBusy('analyze')
    try {
      const result = await api.analyze({ session_id: sessionId, use_ocr: useOcr })
      setReport(result)
      setFindings(result.findings.map((finding) => ({
        ...finding,
        decision: presetDecision(purpose, finding.kind),
        keepLastN: presetMaskLastN(purpose, finding.kind),
      })))
      setSelectedFindingId(result.findings[0]?.id || null)
      setSelectedPage(result.findings[0]?.page || 1)
      setWorkflowStep('review')
      setNotice(`Analysis complete · ${result.findings.length} detection${result.findings.length === 1 ? '' : 's'} ready for review.`)
    } catch (analysisError) {
      setError(getErrorMessage(analysisError))
    } finally {
      setBusy(null)
    }
  }

  const handleExport = async () => {
    if (!sessionId) return
    clearFeedback()
    setBusy('export')
    try {
      const result = await api.export({
        session_id: sessionId,
        use_ocr: useOcr,
        flatten_to_image: report?.document_type === 'pdf' && flattenToImage,
        keep_last_n: keepLastN,
        findings: findings.map(({ id, page, bbox, decision, manual, keepLastN: findingMask }) => ({
          id,
          page,
          bbox,
          decision,
          manual,
          // The global checkbox enables/disables masking; the finding value
          // identifies detections eligible for partial identifier masking.
          keep_last_n: findingMask && keepLastN !== null ? keepLastN : undefined,
        })),
      })
      setExported({ blob: result.blob, filename: result.filename })
      downloadBlob(result.blob, result.filename)
      try {
        const latestReport = await api.report(sessionId)
        setReport(latestReport)
      } catch {
        // The binary export and verification header are already valid even if refreshing the report fails.
      }
      setWorkflowStep('export')
      setNotice('Export verified and downloaded. Keep the file only where it is needed.')
    } catch (exportError) {
      setError(getErrorMessage(exportError))
    } finally {
      setBusy(null)
    }
  }

  const handleDelete = async () => {
    if (!sessionId) return
    if (!window.confirm('Delete this temporary PRIVASHIELD session and all stored exports?')) return
    clearFeedback()
    setBusy('delete')
    try {
      await api.deleteSession(sessionId)
      if (previewAsset) URL.revokeObjectURL(previewAsset.objectUrl)
      setFile(null)
      setPreviewAsset(null)
      setUpload(null)
      setReport(null)
      setFindings([])
      setExported(null)
      setSelectedFindingId(null)
      setSelectedPage(1)
      setManualMode(false)
      setWorkflowStep('upload')
      setNotice('Session deleted. Source, report, and saved export files were removed.')
    } catch (deleteError) {
      setError(getErrorMessage(deleteError))
    } finally {
      setBusy(null)
    }
  }

  const updateDecision = (id: string, decision: Decision) => {
    setFindings((current) => current.map((finding) => (finding.id === id ? { ...finding, decision } : finding)))
  }

  const selectFinding = (finding: ReviewedFinding) => {
    setSelectedFindingId(finding.id)
    setSelectedPage(finding.page)
    if (finding.decision !== 'redact') updateDecision(finding.id, 'redact')
    setWorkflowStep('preview')
  }

  const addManualFinding = (page: number, bbox: Bbox) => {
    const manualFinding: ReviewedFinding = {
      id: makeFindingId(),
      kind: 'manual_redaction',
      page,
      bbox,
      confidence: 1,
      source: 'manual',
      decision: 'redact',
      manual: true,
    }
    setFindings((current) => [...current, manualFinding])
    setSelectedFindingId(manualFinding.id)
    setManualMode(false)
    setNotice('Manual redaction added to the review preview.')
  }

  const navigateStep = (step: WorkflowStep, index: number) => {
    if (index === 0 || (index <= 1 && Boolean(report)) || (index <= 2 && Boolean(report)) || (index === 3 && Boolean(exported))) {
      setWorkflowStep(step)
    }
  }

  return (
    <div className="min-h-screen bg-cloud text-slate-900">
      <header className="no-print border-b border-white/10 bg-ink text-white">
        <div className="noise mx-auto flex max-w-[1520px] items-center justify-between gap-4 px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <div className="relative flex h-10 w-10 items-center justify-center rounded-xl border border-cyan/40 bg-cyan/10 text-cyan">
              <ShieldCheck size={21} strokeWidth={2.2} />
              <span className="absolute -bottom-1 -right-1 h-2.5 w-2.5 rounded-full bg-mint ring-2 ring-ink" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold tracking-[0.18em]">PRIVASHIELD</span>
                <span className="rounded-full border border-white/15 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.17em] text-slate-300">Phase 1</span>
              </div>
              <p className="mt-0.5 text-xs text-slate-400">Private document redaction workspace</p>
            </div>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <div className={`hidden items-center gap-2 rounded-full border px-3 py-1.5 sm:flex ${apiOnline === false ? 'border-rose-300/25 bg-rose-300/10 text-rose-100' : 'border-white/10 bg-white/5 text-slate-300'}`} title={apiMessage}>
              <span className={`h-1.5 w-1.5 rounded-full ${apiOnline === true ? 'bg-mint' : apiOnline === false ? 'bg-rose-300' : 'bg-warning'}`} />
              {apiOnline === true ? 'API connected' : apiOnline === false ? 'API offline' : 'Connecting'}
            </div>
            {sessionId ? (
              <button className="inline-flex items-center gap-2 rounded-lg border border-rose-200/20 bg-rose-200/10 px-3 py-2 font-semibold text-rose-100 transition hover:bg-rose-200/20 disabled:opacity-50" onClick={handleDelete} disabled={busy === 'delete'}>
                {busy === 'delete' ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                Delete session
              </button>
            ) : null}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1520px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
        <div className="no-print mb-5 flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm sm:flex-row sm:items-center sm:justify-between sm:px-5">
          <div className="flex items-start gap-3">
            <LockKeyhole className="mt-0.5 shrink-0 text-cyan" size={17} />
            <div>
              <p className="text-sm font-semibold text-navy">Temporary by design</p>
              <p className="text-xs leading-5 text-slate-500">Your source stays inside the temporary server session until you delete it or the session expires.</p>
            </div>
          </div>
          <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500"><Shield size={14} /> Values stay out of the report UI</span>
        </div>

        {(error || notice) && (
          <div className={`no-print mb-5 flex items-start gap-3 rounded-2xl border px-4 py-3 text-sm ${error ? 'border-rose-200 bg-rose-50 text-rose-900' : 'border-emerald-200 bg-emerald-50 text-emerald-900'}`} role="status" aria-live="polite">
            {error ? <AlertTriangle size={18} className="mt-0.5 shrink-0" /> : <CheckCircle2 size={18} className="mt-0.5 shrink-0" />}
            <span className="flex-1 leading-6">{error || notice}</span>
            <button className="rounded-md p-1 opacity-70 hover:bg-black/5 hover:opacity-100" onClick={clearFeedback} aria-label="Dismiss message"><X size={16} /></button>
          </div>
        )}

        <WorkflowStepper activeStep={workflowStep} activeIndex={stepIndex} onNavigate={navigateStep} />

        {!file ? (
          <UploadLanding fileInputRef={fileInputRef} fileError={fileError} onFile={acceptFile} />
        ) : (
          <>
            <FileSummary file={file} upload={upload} fileError={fileError} busy={busy} onUpload={handleUpload} onChooseAnother={() => fileInputRef.current?.click()} fileInputRef={fileInputRef} onFile={acceptFile} />

            {!report ? (
              <AnalysisSetup
                purpose={purpose}
                purposeId={purposeId}
                setPurposeId={setPurposeId}
                useOcr={useOcr}
                setUseOcr={setUseOcr}
                uploaded={Boolean(upload)}
                busy={busy}
                onAnalyze={handleAnalyze}
              />
            ) : (
              <div className="mt-6 grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_390px]">
                <PreviewSurface
                  file={file}
                  previewAsset={previewAsset}
                  sessionId={sessionId}
                  documentType={report.document_type}
                  page={selectedPage}
                  pageCount={pageCount}
                  findings={currentPageFindings}
                  selectedFindingId={selectedFindingId}
                  imageSize={imageSize}
                  setImageSize={setImageSize}
                  manualMode={manualMode}
                  setManualMode={setManualMode}
                  onPageChange={setSelectedPage}
                  onSelectFinding={selectFinding}
                  onCreateManual={addManualFinding}
                />
                <aside className="space-y-5">
                  <DetectionPanel
                    findings={findings}
                    maskLastN={keepLastN}
                    selectedFindingId={selectedFindingId}
                    onSelect={selectFinding}
                    onDecision={updateDecision}
                    manualMode={manualMode}
                    setManualMode={setManualMode}
                  />
                  <ExportPanel
                    flattenToImage={flattenToImage}
                    setFlattenToImage={setFlattenToImage}
                    documentType={report.document_type}
                    keepLastN={keepLastN}
                    setKeepLastN={setKeepLastN}
                    busy={busy}
                    exported={exported}
                    redactedCount={redactedCount}
                    onExport={handleExport}
                    onDownload={() => exported && downloadBlob(exported.blob, exported.filename)}
                  />
                </aside>
              </div>
            )}

            {report ? <PrivacyReport report={report} onDownloadJson={() => downloadJson(report, `privashield-report-${report.report_id}.json`)} onPrint={() => window.print()} /> : null}
            {report && exported ? <BeforeAfterPreview file={file} previewAsset={previewAsset} sessionId={sessionId} page={selectedPage} documentType={report.document_type} exported={exported} /> : null}
          </>
        )}
      </main>

      <footer className="no-print mx-auto flex max-w-[1520px] flex-col gap-2 px-4 pb-8 text-xs text-slate-400 sm:flex-row sm:items-center sm:justify-between sm:px-6 lg:px-8">
        <span>PRIVASHIELD Phase 1 · detection coverage should be evaluated against your documents and threat model.</span>
        <span className="inline-flex items-center gap-1.5"><CircleHelp size={13} /> No legal-compliance or perfect-detection claims</span>
      </footer>
    </div>
  )
}

function BeforeAfterPreview({ file, previewAsset, sessionId, page, documentType, exported }: { file: File; previewAsset: PreviewAsset | null; sessionId: string | null; page: number; documentType: DocumentType; exported: { blob: Blob; filename: string } }) {
  const [zoom, setZoom] = useState(100)
  const [afterUrl, setAfterUrl] = useState<string | null>(null)
  const leftScroll = useRef<HTMLDivElement>(null)
  const rightScroll = useRef<HTMLDivElement>(null)
  const syncing = useRef(false)
  const beforeSource = documentType === 'pdf' && sessionId ? api.previewUrl(sessionId, page) : previewAsset?.pageUrl(page)

  useEffect(() => {
    const url = URL.createObjectURL(exported.blob)
    setAfterUrl(url)

    return () => URL.revokeObjectURL(url)
  }, [exported.blob])

  const syncScroll = (source: 'left' | 'right') => {
    if (syncing.current) return
    syncing.current = true
    const from = source === 'left' ? leftScroll.current : rightScroll.current
    const to = source === 'left' ? rightScroll.current : leftScroll.current
    if (from && to) {
      to.scrollTop = from.scrollTop
      to.scrollLeft = from.scrollLeft
    }
    requestAnimationFrame(() => { syncing.current = false })
  }

  return <section className="no-print panel mt-6 overflow-hidden"><div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 py-4 sm:px-5"><div><p className="eyebrow">Before / after</p><h2 className="mt-1 text-lg font-bold text-navy">Compare the exported copy</h2><p className="mt-1 text-xs text-slate-500">The panes share zoom and scroll position. Review the result again before sharing.</p></div><div className="flex items-center gap-2"><button className="btn-quiet border border-slate-200" onClick={() => setZoom((value) => Math.max(75, value - 10))} aria-label="Zoom out"><Minus size={14} /></button><span className="min-w-[48px] text-center text-xs font-bold text-slate-500">{zoom}%</span><button className="btn-quiet border border-slate-200" onClick={() => setZoom((value) => Math.min(125, value + 10))} aria-label="Zoom in"><Plus size={14} /></button></div></div><div className="grid gap-4 bg-[#e9eef3] p-4 lg:grid-cols-2"><ComparePane label={`Before · ${file.name}`} scrollRef={leftScroll} onScroll={() => syncScroll('left')}><img src={beforeSource} alt="Original document page" className="max-w-none bg-white shadow-float" style={{ transform: `scale(${zoom / 100})`, transformOrigin: 'top left' }} /></ComparePane><ComparePane label="After · verified export" scrollRef={rightScroll} onScroll={() => syncScroll('right')}>{afterUrl ? (documentType === 'image' ? <img src={afterUrl} alt="Verified redacted export" className="max-w-none bg-white shadow-float" style={{ transform: `scale(${zoom / 100})`, transformOrigin: 'top left' }} /> : <iframe src={`${afterUrl}#page=${page}&view=FitH`} title="Verified redacted export" className="h-[430px] min-w-full border-0 bg-white" style={{ transform: `scale(${zoom / 100})`, transformOrigin: 'top left' }} />) : <div className="flex h-[430px] items-center justify-center text-sm text-slate-400">Preparing verified preview…</div>}</ComparePane></div></section>
}

function ComparePane({ label, children, scrollRef, onScroll }: { label: string; children: React.ReactNode; scrollRef: React.RefObject<HTMLDivElement>; onScroll: () => void }) {
  return <div className="min-w-0"><p className="mb-2 text-[10px] font-bold uppercase tracking-[0.16em] text-slate-500">{label}</p><div ref={scrollRef} onScroll={onScroll} className="h-[440px] overflow-auto rounded-xl border border-slate-200 bg-white p-3">{children}</div></div>
}

function WorkflowStepper({ activeStep, activeIndex, onNavigate }: { activeStep: WorkflowStep; activeIndex: number; onNavigate: (step: WorkflowStep, index: number) => void }) {
  return (
    <nav className="no-print panel overflow-hidden" aria-label="Document workflow">
      <ol className="grid grid-cols-2 divide-y divide-slate-100 sm:grid-cols-4 sm:divide-x sm:divide-y-0">
        {STEPS.map((step, index) => {
          const complete = index < activeIndex
          const active = activeStep === step.id
          return (
            <li key={step.id}>
              <button className={`flex w-full items-center gap-3 px-4 py-3.5 text-left transition sm:px-5 ${active ? 'bg-slate-50' : 'hover:bg-slate-50/70'}`} onClick={() => onNavigate(step.id, index)} aria-current={active ? 'step' : undefined}>
                <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full border text-xs font-bold ${complete ? 'border-cyan bg-cyan text-ink' : active ? 'border-ink bg-ink text-white' : 'border-slate-200 bg-white text-slate-400'}`}>
                  {complete ? <Check size={15} strokeWidth={3} /> : `0${index + 1}`}
                </span>
                <span className="min-w-0">
                  <span className={`block text-sm font-bold ${active ? 'text-navy' : 'text-slate-500'}`}>{step.label}</span>
                  <span className="block truncate text-[11px] text-slate-400">{step.helper}</span>
                </span>
              </button>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}

function UploadLanding({ fileInputRef, fileError, onFile }: { fileInputRef: React.RefObject<HTMLInputElement>; fileError: string | null; onFile: (file: File | undefined) => void }) {
  const [dragging, setDragging] = useState(false)
  return (
    <section className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1.3fr)_390px]">
      <div className="relative overflow-hidden rounded-3xl bg-ink px-5 py-7 text-white shadow-float sm:px-8 sm:py-10 lg:px-12 lg:py-14">
        <div className="absolute -right-20 -top-24 h-72 w-72 rounded-full border border-cyan/20 bg-cyan/5 blur-2xl" />
        <div className="relative max-w-2xl">
          <div className="mb-7 inline-flex items-center gap-2 rounded-full border border-cyan/20 bg-cyan/10 px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.18em] text-mint"><WandSparkles size={13} /> Redact before sharing</div>
          <h1 className="max-w-xl text-3xl font-bold leading-tight tracking-[-0.04em] sm:text-5xl">Remove sensitive details with a clear review trail.</h1>
          <p className="mt-5 max-w-xl text-sm leading-6 text-slate-300 sm:text-base">Upload one document, inspect what was detected, and export a verified redacted copy. Every session is temporary and every report is value-free.</p>
          <div className="mt-9 flex flex-wrap gap-2 text-xs font-semibold text-slate-300">
            <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5">PDF · JPG · PNG</span>
            <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5">10 MB max</span>
            <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5">Up to 5 PDF pages</span>
          </div>
        </div>
      </div>
      <div className="panel p-4 sm:p-5">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <p className="eyebrow">Start a session</p>
            <h2 className="mt-1 text-xl font-bold tracking-tight text-navy">Add a document</h2>
          </div>
          <div className="rounded-xl bg-cyan/10 p-2.5 text-cyan"><CloudUpload size={20} /></div>
        </div>
        <input ref={fileInputRef} className="sr-only" type="file" accept={ACCEPTED_EXTENSIONS} onChange={(event) => onFile(event.target.files?.[0])} />
        <div
          className={`rounded-2xl border-2 border-dashed px-5 py-9 text-center transition ${dragging ? 'border-cyan bg-cyan/5' : 'border-slate-200 bg-slate-50 hover:border-slate-300'} ${fileError ? 'border-rose-300 bg-rose-50/50' : ''}`}
          role="button"
          tabIndex={0}
          onClick={() => fileInputRef.current?.click()}
          onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); fileInputRef.current?.click() } }}
          onDragEnter={(event) => { event.preventDefault(); setDragging(true) }}
          onDragOver={(event) => event.preventDefault()}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => { event.preventDefault(); setDragging(false); onFile(event.dataTransfer.files[0]) }}
          aria-label="Upload PDF, JPG, or PNG"
        >
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-white text-slate-500 shadow-sm"><UploadCloud size={23} /></div>
          <p className="mt-4 text-sm font-bold text-navy">Drop your file here</p>
          <p className="mt-1 text-xs text-slate-500">or <span className="font-semibold text-cyan-700">browse from device</span></p>
          <p className="mt-5 text-[11px] leading-5 text-slate-400">Only PDF, JPG, and PNG · maximum 10 MB<br />Your file is uploaded only when you continue.</p>
        </div>
        {fileError ? <p className="mt-3 flex items-start gap-2 text-xs font-semibold leading-5 text-rose-700" role="alert"><AlertTriangle size={14} className="mt-0.5 shrink-0" />{fileError}</p> : null}
        <div className="mt-5 flex items-start gap-2 border-t border-slate-100 pt-4 text-[11px] leading-5 text-slate-500"><LockKeyhole size={14} className="mt-0.5 shrink-0 text-cyan" />Temporary storage is cleared when you delete the session or the server TTL expires.</div>
      </div>
    </section>
  )
}

function FileSummary({ file, upload, fileError, busy, onUpload, onChooseAnother, fileInputRef, onFile }: { file: File; upload: UploadResponse | null; fileError: string | null; busy: BusyState; onUpload: () => void; onChooseAnother: () => void; fileInputRef: React.RefObject<HTMLInputElement>; onFile: (file: File | undefined) => void }) {
  return (
    <section className="no-print panel mt-6 p-4 sm:p-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-slate-600">{file.type === 'application/pdf' ? <FileText size={21} /> : <FileImage size={21} />}</div>
          <div className="min-w-0">
            <p className="truncate text-sm font-bold text-navy">{file.name}</p>
            <p className="mt-0.5 text-xs text-slate-500">{formatBytes(file.size)} · {file.type === 'application/pdf' ? 'PDF document' : 'Image document'}{upload ? ` · ${upload.pages} page${upload.pages === 1 ? '' : 's'}` : ''}</p>
          </div>
          {upload ? <span className="hidden items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-bold text-emerald-700 sm:inline-flex"><CheckCircle2 size={13} /> Uploaded</span> : null}
        </div>
        <div className="flex flex-wrap gap-2">
          {!upload ? <button className="btn-primary" onClick={onUpload} disabled={busy === 'upload'}>{busy === 'upload' ? <Loader2 size={16} className="animate-spin" /> : <ArrowUpIcon />} {busy === 'upload' ? 'Uploading…' : 'Upload securely'}</button> : null}
          <input ref={fileInputRef} className="sr-only" type="file" accept={ACCEPTED_EXTENSIONS} onChange={(event) => onFile(event.target.files?.[0])} />
          <button className="btn-secondary" onClick={onChooseAnother}><RotateCcw size={15} /> Choose another</button>
        </div>
      </div>
      {fileError ? <p className="mt-3 flex items-start gap-2 text-xs font-semibold leading-5 text-rose-700" role="alert"><AlertTriangle size={14} className="mt-0.5 shrink-0" />{fileError}</p> : null}
    </section>
  )
}

function ArrowUpIcon() {
  return <ArrowRight size={16} />
}

function AnalysisSetup({ purpose, purposeId, setPurposeId, useOcr, setUseOcr, uploaded, busy, onAnalyze }: { purpose: PurposePreset; purposeId: string; setPurposeId: (id: string) => void; useOcr: boolean; setUseOcr: (value: boolean) => void; uploaded: boolean; busy: BusyState; onAnalyze: () => void }) {
  return (
    <section className="no-print mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_330px]">
      <div className="panel p-5 sm:p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="eyebrow">Analysis setup</p>
            <h2 className="mt-1 text-2xl font-bold tracking-tight text-navy">Choose a review purpose</h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">Presets guide attention only. The core detection set remains enabled for every purpose.</p>
          </div>
          <div className="hidden rounded-xl bg-slate-100 p-2.5 text-slate-600 sm:block"><ScanSearch size={20} /></div>
        </div>
        <div className="mt-6 grid gap-3 sm:grid-cols-3">
          {PURPOSE_PRESETS.map((preset) => <button key={preset.id} className={`rounded-2xl border p-4 text-left transition ${purposeId === preset.id ? 'border-cyan bg-cyan/5 shadow-sm' : 'border-slate-200 hover:border-slate-300'}`} onClick={() => setPurposeId(preset.id)} aria-pressed={purposeId === preset.id}><span className="block text-sm font-bold text-navy">{preset.label}</span><span className="mt-1 block text-xs leading-5 text-slate-500">{preset.description}</span></button>)}
        </div>
        <div className="mt-5 flex flex-col gap-3 rounded-2xl bg-slate-50 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div><p className="text-sm font-bold text-navy">{purpose.label} focus</p><div className="mt-2 flex flex-wrap gap-1.5">{purpose.focus.map((item) => <span key={item} className="rounded-full bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-600 shadow-sm">{item}</span>)}</div></div>
          <div className="flex items-start gap-2 text-xs leading-5 text-slate-500 sm:max-w-[240px]"><Info size={15} className="mt-0.5 shrink-0 text-cyan" />Purpose settings never reduce the detection coverage.</div>
        </div>
      </div>
      <div className="panel flex flex-col p-5 sm:p-6">
        <p className="eyebrow">Detection engine</p>
        <h3 className="mt-1 text-lg font-bold text-navy">Ready when you are</h3>
        <label className="mt-5 flex cursor-pointer items-start gap-3 rounded-xl border border-slate-200 p-3.5 transition hover:border-slate-300"><input type="checkbox" className="mt-0.5 h-4 w-4 accent-cyan" checked={useOcr} onChange={(event) => setUseOcr(event.target.checked)} /><span><span className="block text-sm font-semibold text-navy">Use OCR when needed</span><span className="mt-1 block text-xs leading-5 text-slate-500">Helps with image-only pages when the optional OCR runtime is available.</span></span></label>
        <div className="mt-4 flex items-start gap-2 text-xs leading-5 text-slate-500"><ShieldCheck size={15} className="mt-0.5 shrink-0 text-cyan" />Reports include categories, confidence, and boxes — never the matched values.</div>
        <button className="btn-primary mt-6 w-full" onClick={onAnalyze} disabled={!uploaded || busy === 'analyze'}>{busy === 'analyze' ? <Loader2 size={17} className="animate-spin" /> : <ScanSearch size={17} />}{busy === 'analyze' ? 'Analyzing…' : uploaded ? 'Analyze document' : 'Upload to continue'}</button>
      </div>
    </section>
  )
}

function PreviewSurface({ file, previewAsset, sessionId, documentType, page, pageCount, findings, selectedFindingId, imageSize, setImageSize, manualMode, setManualMode, onPageChange, onSelectFinding, onCreateManual }: { file: File; previewAsset: PreviewAsset | null; sessionId: string | null; documentType: DocumentType; page: number; pageCount: number; findings: ReviewedFinding[]; selectedFindingId: string | null; imageSize: { width: number; height: number } | null; setImageSize: (size: { width: number; height: number }) => void; manualMode: boolean; setManualMode: (value: boolean) => void; onPageChange: (page: number) => void; onSelectFinding: (finding: ReviewedFinding) => void; onCreateManual: (page: number, bbox: Bbox) => void }) {
  const [zoom, setZoom] = useState(100)
  const [draft, setDraft] = useState<{ start: Point; current: Point } | null>(null)
  const pageSize = imageSize || FALLBACK_PAGE_SIZE
  const pageSource = documentType === 'pdf' && sessionId ? api.previewUrl(sessionId, page) : previewAsset?.pageUrl(page)
  const imagePreview = Boolean(pageSource)

  const pointFromEvent = (event: ReactPointerEvent<HTMLDivElement>): Point => {
    const rect = event.currentTarget.getBoundingClientRect()
    return {
      x: Math.max(0, Math.min(pageSize.width, ((event.clientX - rect.left) / rect.width) * pageSize.width)),
      y: Math.max(0, Math.min(pageSize.height, ((event.clientY - rect.top) / rect.height) * pageSize.height)),
    }
  }

  const pointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!manualMode) return
    event.currentTarget.setPointerCapture(event.pointerId)
    const point = pointFromEvent(event)
    setDraft({ start: point, current: point })
  }

  const pointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!draft) return
    setDraft({ ...draft, current: pointFromEvent(event) })
  }

  const pointerUp = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!draft) return
    const end = pointFromEvent(event)
    const bbox = normalizedBbox([Math.min(draft.start.x, end.x), Math.min(draft.start.y, end.y), Math.max(draft.start.x, end.x), Math.max(draft.start.y, end.y)], pageSize)
    setDraft(null)
    if (bbox[2] - bbox[0] > 8 && bbox[3] - bbox[1] > 8) onCreateManual(page, bbox)
  }

  const renderBox = (finding: ReviewedFinding, key: string) => {
    const [x0, y0, x1, y1] = finding.bbox
    const tone = confidenceTone(finding.confidence)
    const selected = selectedFindingId === finding.id
    const style = { left: `${(x0 / pageSize.width) * 100}%`, top: `${(y0 / pageSize.height) * 100}%`, width: `${((x1 - x0) / pageSize.width) * 100}%`, height: `${((y1 - y0) / pageSize.height) * 100}%` }
    return <button key={key} type="button" className={`absolute rounded-sm border-2 text-left transition ${finding.decision === 'keep' ? 'border-slate-400 bg-slate-400/10 opacity-55' : tone === 'low' ? 'border-warning bg-warning/20' : 'border-cyan bg-cyan/20'} ${selected ? 'z-10 ring-2 ring-white ring-offset-1' : ''} ${manualMode ? 'pointer-events-none' : ''}`} style={style} onClick={(event) => { event.stopPropagation(); onSelectFinding(finding) }} aria-label={`${humanizeKind(finding.kind)} detection, ${finding.decision === 'redact' ? 'redact' : 'keep'}`}>
      <span className="absolute -top-5 left-0 whitespace-nowrap rounded bg-ink px-1.5 py-0.5 text-[9px] font-bold text-white shadow-sm">{finding.manual ? 'MANUAL' : humanizeKind(finding.kind)}</span>
    </button>
  }

  return (
    <section className="no-print panel overflow-hidden">
      <div className="flex flex-col gap-3 border-b border-slate-100 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
        <div><div className="flex items-center gap-2"><p className="eyebrow">Preview</p><span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-500">PAGE {page} / {pageCount}</span></div><h2 className="mt-1 text-lg font-bold text-navy">Inspect the redaction map</h2></div>
        <div className="flex items-center gap-1.5"><button className="btn-quiet border border-slate-200" onClick={() => setZoom((current) => Math.max(75, current - 10))} aria-label="Zoom out" title="Zoom out"><Minus size={15} /></button><span className="min-w-[48px] text-center text-xs font-bold text-slate-500">{zoom}%</span><button className="btn-quiet border border-slate-200" onClick={() => setZoom((current) => Math.min(125, current + 10))} aria-label="Zoom in" title="Zoom in"><Plus size={15} /></button></div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 bg-slate-50/70 px-4 py-3 sm:px-5">
        <div className="flex items-center gap-2"><button className="btn-quiet border border-slate-200 bg-white" onClick={() => onPageChange(Math.max(1, page - 1))} disabled={page === 1} aria-label="Previous page"><ArrowLeft size={14} /> <span className="hidden sm:inline">Previous</span></button><button className="btn-quiet border border-slate-200 bg-white" onClick={() => onPageChange(Math.min(pageCount, page + 1))} disabled={page === pageCount} aria-label="Next page"><span className="hidden sm:inline">Next</span><ArrowRight size={14} /></button></div>
        <button className={`btn-quiet border ${manualMode ? 'border-cyan bg-cyan/10 text-cyan-800' : 'border-slate-200 bg-white'}`} onClick={() => { setManualMode(!manualMode); setDraft(null) }} aria-pressed={manualMode}><Maximize2 size={14} /> {manualMode ? 'Draw a box on the page' : 'Add manual redaction'}</button>
      </div>
      <div className="bg-[#e9eef3] p-4 sm:p-6">
        {imagePreview ? (
          <div className="checkerboard overflow-auto rounded-xl border border-slate-200 p-3 shadow-inner">
            <div className="relative mx-auto w-fit max-w-full transition-transform" style={{ transform: `scale(${zoom / 100})`, transformOrigin: 'top center' }}>
              <img src={pageSource} alt={`Page ${page} of ${file.name}`} className="block max-h-[620px] max-w-full rounded-sm bg-white shadow-float" onLoad={(event) => setImageSize({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })} />
              <div className={`absolute inset-0 ${manualMode ? 'cursor-crosshair' : ''}`} onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp} role={manualMode ? 'application' : undefined} aria-label={manualMode ? 'Draw a manual redaction rectangle' : 'Document redaction overlay'}>
                {findings.map((finding) => renderBox(finding, finding.id))}
                {draft ? <DraftBox draft={draft} pageSize={pageSize} /> : null}
              </div>
            </div>
          </div>
        ) : (
          <div className="flex min-h-[360px] items-center justify-center rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">The page preview is not available yet. Upload the document to render it here.</div>
        )}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 px-4 py-3 text-xs text-slate-500 sm:px-5"><span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-cyan" />Redact <span className="ml-2 h-2 w-2 rounded-full bg-slate-400" />Keep</span><span>{findings.length} area{findings.length === 1 ? '' : 's'} on this page · overlay is a review aid</span></div>
    </section>
  )
}

function DraftBox({ draft, pageSize }: { draft: { start: Point; current: Point }; pageSize: { width: number; height: number } }) {
  const x0 = Math.min(draft.start.x, draft.current.x)
  const y0 = Math.min(draft.start.y, draft.current.y)
  const x1 = Math.max(draft.start.x, draft.current.x)
  const y1 = Math.max(draft.start.y, draft.current.y)
  return <div className="pointer-events-none absolute rounded-sm border-2 border-dashed border-ink bg-ink/20" style={{ left: `${(x0 / pageSize.width) * 100}%`, top: `${(y0 / pageSize.height) * 100}%`, width: `${((x1 - x0) / pageSize.width) * 100}%`, height: `${((y1 - y0) / pageSize.height) * 100}%` }} />
}

function DetectionPanel({ findings, maskLastN, selectedFindingId, onSelect, onDecision, manualMode, setManualMode }: { findings: ReviewedFinding[]; maskLastN: number | null; selectedFindingId: string | null; onSelect: (finding: ReviewedFinding) => void; onDecision: (id: string, decision: Decision) => void; manualMode: boolean; setManualMode: (value: boolean) => void }) {
  const sortedFindings = [...findings].sort((a, b) => a.page - b.page || a.bbox[1] - b.bbox[1])
  const lowConfidenceCount = findings.filter((finding) => finding.confidence < 0.8).length
  return (
    <section className="no-print panel overflow-hidden">
      <div className="border-b border-slate-100 px-4 py-4 sm:px-5"><div className="flex items-start justify-between gap-3"><div><p className="eyebrow">Review queue</p><h2 className="mt-1 text-lg font-bold text-navy">Detections <span className="text-slate-400">({findings.length})</span></h2></div><div className="rounded-xl bg-cyan/10 p-2 text-cyan"><PanelRight size={18} /></div></div><p className="mt-2 text-xs leading-5 text-slate-500">Click an area or use the decision controls. Values are intentionally not shown.</p>{lowConfidenceCount > 0 ? <div className="mt-3 flex items-start gap-2 rounded-xl border border-warning/30 bg-warning/10 px-3 py-2.5 text-xs leading-5 text-amber-900"><AlertTriangle size={14} className="mt-0.5 shrink-0" /><span><strong>{lowConfidenceCount} low-confidence area{lowConfidenceCount === 1 ? '' : 's'}.</strong> Review the highlighted boxes manually.</span></div> : null}</div>
      <div className="max-h-[510px] overflow-y-auto p-3">
         {sortedFindings.length === 0 ? <div className="rounded-xl border border-dashed border-slate-200 px-4 py-8 text-center"><ClipboardCheck className="mx-auto text-slate-300" size={27} /><p className="mt-3 text-sm font-semibold text-slate-600">No areas detected</p><p className="mt-1 text-xs leading-5 text-slate-400">You can still add a manual redaction rectangle in the preview.</p></div> : sortedFindings.map((finding, index) => <FindingRow key={finding.id} finding={finding} maskLastN={maskLastN} index={index} selected={selectedFindingId === finding.id} onSelect={onSelect} onDecision={onDecision} />)}
      </div>
      <div className="border-t border-slate-100 bg-slate-50/70 p-3"><button className={`flex w-full items-center justify-center gap-2 rounded-xl border px-3 py-2.5 text-xs font-bold transition ${manualMode ? 'border-cyan bg-cyan/10 text-cyan-800' : 'border-slate-200 bg-white text-navy hover:border-slate-300'}`} onClick={() => setManualMode(!manualMode)} aria-pressed={manualMode}><Maximize2 size={14} />{manualMode ? 'Manual mode active · draw on preview' : 'Add a manual redaction area'}</button><p className="mt-2 text-center text-[10px] leading-4 text-slate-400">Manual rectangles and Keep decisions are sent to the backend and verified with the export.</p></div>
    </section>
  )
}

function FindingRow({ finding, maskLastN, index, selected, onSelect, onDecision }: { finding: ReviewedFinding; maskLastN: number | null; index: number; selected: boolean; onSelect: (finding: ReviewedFinding) => void; onDecision: (id: string, decision: Decision) => void }) {
  const tone = confidenceTone(finding.confidence)
  return (
    <div className={`mb-2 rounded-xl border p-3 transition ${selected ? 'border-cyan bg-cyan/5 shadow-sm' : 'border-slate-200 bg-white hover:border-slate-300'}`}>
      <div className="flex items-start gap-2.5">
        <button className="min-w-0 flex-1 text-left" onClick={() => onSelect(finding)} aria-label={`Review ${humanizeKind(finding.kind)} on page ${finding.page}`}>
           <span className="flex items-center gap-2"><span className={`h-2 w-2 shrink-0 rounded-full ${finding.decision === 'keep' ? 'bg-slate-400' : tone === 'low' ? 'bg-warning' : 'bg-cyan'}`} /><span className="truncate text-sm font-bold text-navy">{finding.manual ? 'Manual redaction' : humanizeKind(finding.kind)}</span>{finding.manual ? <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[9px] font-bold uppercase text-slate-500">Added</span> : null}{finding.keepLastN && maskLastN !== null ? <span className="rounded bg-cyan/10 px-1.5 py-0.5 text-[9px] font-bold uppercase text-cyan-800">Last {maskLastN}</span> : null}</span>
          <span className="mt-1 block text-[11px] text-slate-500">Page {finding.page} · {finding.source} · {confidencePercent(finding.confidence)} confidence</span>
        </button>
        <span className={`rounded-full px-2 py-1 text-[10px] font-bold ${tone === 'high' ? 'bg-emerald-50 text-emerald-700' : tone === 'medium' ? 'bg-sky-50 text-sky-700' : 'bg-amber-50 text-amber-700'}`}>{tone}</span>
      </div>
      <div className="mt-3 flex items-center gap-1.5"><button className={`flex-1 rounded-lg px-2 py-1.5 text-[11px] font-bold transition ${finding.decision === 'redact' ? 'bg-ink text-white' : 'bg-slate-100 text-slate-500 hover:bg-slate-200'}`} onClick={() => onDecision(finding.id, 'redact')} aria-pressed={finding.decision === 'redact'}><Shield size={12} className="mr-1 inline" />Redact</button><button className={`flex-1 rounded-lg px-2 py-1.5 text-[11px] font-bold transition ${finding.decision === 'keep' ? 'bg-slate-600 text-white' : 'bg-slate-100 text-slate-500 hover:bg-slate-200'}`} onClick={() => onDecision(finding.id, 'keep')} aria-pressed={finding.decision === 'keep'}>Keep</button><span className="px-1 text-[10px] text-slate-400">#{String(index + 1).padStart(2, '0')}</span></div>
    </div>
  )
}

function ExportPanel({ flattenToImage, setFlattenToImage, documentType, keepLastN, setKeepLastN, busy, exported, redactedCount, onExport, onDownload }: { flattenToImage: boolean; setFlattenToImage: (value: boolean) => void; documentType: DocumentType; keepLastN: number | null; setKeepLastN: (value: number | null) => void; busy: BusyState; exported: { blob: Blob; filename: string } | null; redactedCount: number; onExport: () => void; onDownload: () => void }) {
  const isPdf = documentType === 'pdf'
  return (
    <section className="no-print panel overflow-hidden">
      <div className="bg-ink px-4 py-4 text-white sm:px-5"><div className="flex items-center justify-between gap-3"><div><p className="text-[10px] font-bold uppercase tracking-[0.22em] text-cyan">Export</p><h2 className="mt-1 text-lg font-bold">Create a safe copy</h2></div><ArrowDownToLine className="text-mint" size={20} /></div><p className="mt-2 text-xs leading-5 text-slate-300">The API verifies the output before returning the file.</p></div>
      <div className="space-y-4 p-4 sm:p-5">
         <label className={`flex items-start gap-3 rounded-xl border border-slate-200 p-3 ${isPdf ? 'cursor-pointer' : 'cursor-not-allowed bg-slate-50/70'}`}><input type="checkbox" className="mt-0.5 h-4 w-4 accent-cyan" checked={isPdf && flattenToImage} disabled={!isPdf} onChange={(event) => setFlattenToImage(event.target.checked)} /><span><span className="block text-sm font-bold text-navy">Flatten PDF to image</span><span className="mt-1 block text-xs leading-5 text-slate-500">{isPdf ? 'Rasterizes each page to remove text-layer remnants.' : 'Not needed for images; this upload is already rasterized.'}</span></span></label>
         <label className="block"><span className="flex items-center justify-between text-sm font-bold text-navy"><span>Partial mask for detected identifiers</span><span className="text-xs font-normal text-slate-400">optional</span></span><div className="mt-2 flex items-center gap-2"><input type="checkbox" className="h-4 w-4 accent-cyan" checked={keepLastN !== null} onChange={(event) => setKeepLastN(event.target.checked ? 4 : null)} /><span className="text-xs text-slate-500">Keep last</span><input type="number" min={1} max={20} value={keepLastN ?? 4} disabled={keepLastN === null} onChange={(event) => setKeepLastN(Math.max(1, Math.min(20, Number(event.target.value) || 1)))} className="w-20 rounded-lg border border-slate-200 px-3 py-2 text-sm font-semibold text-navy disabled:bg-slate-50 disabled:text-slate-400" /><span className="text-xs text-slate-500">characters</span></div><p className="mt-1 text-[11px] leading-5 text-slate-400">When enabled, eligible identifiers such as PAN, Aadhaar, and passport detections keep their final characters. Other fields remain fully redacted.</p></label>
        <div className="flex items-start gap-2 rounded-xl bg-slate-50 p-3 text-xs leading-5 text-slate-500"><FileCheck2 size={15} className="mt-0.5 shrink-0 text-cyan" />{redactedCount} area{redactedCount === 1 ? '' : 's'} marked for the review preview. Server verification checks text, bytes, metadata, and annotations.</div>
        <button className="btn-primary w-full" onClick={onExport} disabled={busy === 'export'}>{busy === 'export' ? <Loader2 size={17} className="animate-spin" /> : <Download size={17} />}{busy === 'export' ? 'Verifying export…' : 'Export redacted file'}</button>
        {exported ? <button className="btn-secondary w-full" onClick={onDownload}><ArrowDownToLine size={16} /> Download again · {exported.filename}</button> : null}
      </div>
    </section>
  )
}

function PrivacyReport({ report, onDownloadJson, onPrint }: { report: ReportResponse; onDownloadJson: () => void; onPrint: () => void }) {
  const detectedCount = report.detected_count || report.findings.length
  const redactedCategories = Object.entries(report.redacted_categories || {}).sort((a, b) => b[1] - a[1])
  const keptCategories = Object.entries(report.kept_categories || {}).sort((a, b) => b[1] - a[1])
  return (
    <section className="print-panel panel mt-6 overflow-hidden">
      <div className="no-print flex flex-col gap-3 border-b border-slate-100 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-5"><div><p className="eyebrow">Privacy report</p><h2 className="mt-1 text-xl font-bold tracking-tight text-navy">A value-free verification summary</h2></div><div className="flex flex-wrap gap-2"><button className="btn-secondary" onClick={onDownloadJson}><FileJson size={15} /> Download JSON</button><button className="btn-secondary" onClick={onPrint}><Printer size={15} /> Print view</button></div></div>
       <div className="p-4 sm:p-6"><div className="flex flex-col gap-4 border-b border-slate-100 pb-5 sm:flex-row sm:items-end sm:justify-between"><div><p className="text-xs font-semibold uppercase tracking-[0.15em] text-slate-400">Report {report.report_id}</p><h3 className="mt-2 text-2xl font-bold tracking-tight text-navy">{detectedCount} sensitive area{detectedCount === 1 ? '' : 's'} detected</h3><p className="mt-1 text-sm text-slate-500">{report.pages} page{report.pages === 1 ? '' : 's'} · {report.document_type.toUpperCase()} · created {new Date(report.created_at).toLocaleString()}</p></div>{report.verification ? <VerificationBadge verification={report.verification} /> : <span className="inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-2 text-xs font-bold text-slate-600"><Info size={14} /> Export not verified yet</span>}</div>
         <div className="mt-5 grid gap-3 sm:grid-cols-3"><SummaryStat label="Detected" value={detectedCount} /><SummaryStat label="Redacted" value={report.redacted_count} tone="cyan" /><SummaryStat label="Kept" value={report.kept_count} tone="slate" /></div>
         <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]"><CategoryList title="Redacted categories" items={redactedCategories} empty="No fields were marked for redaction." /><CategoryList title="Kept categories" items={keptCategories} empty="No fields were kept in the reviewed export." /></div>
         <div className="mt-6 grid gap-4 border-t border-slate-100 pt-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]"><div><p className="eyebrow">Verification results</p><div className="mt-3 grid gap-2 sm:grid-cols-2">{report.verification ? <><VerificationItem label="Text absent" passed={report.verification.text_absent} /><VerificationItem label="Raw bytes absent" passed={report.verification.raw_bytes_absent} /><VerificationItem label="Metadata stripped" passed={report.verification.metadata_clean} /><VerificationItem label="Annotations clean" passed={report.verification.annotations_clean} /><VerificationItem label={`OCR · ${report.verification.ocr}`} passed={report.verification.ocr !== 'failed'} /></> : <p className="text-sm text-slate-500">Export to run post-export verification.</p>}</div></div><div><p className="eyebrow">Per-field checks</p><div className="mt-3 space-y-2">{report.verification?.fields?.length ? report.verification.fields.map((field) => <div key={field.id} className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 px-3 py-2.5 text-xs"><span className="font-semibold text-navy">{humanizeKind(field.kind)}</span><span className={field.passed ? 'font-bold text-emerald-700' : 'font-bold text-rose-700'}>{field.passed ? 'passed' : 'needs review'}</span></div>) : <p className="text-sm text-slate-500">Field-level results appear after export.</p>}</div></div></div>
         <div className="mt-6 grid gap-4 border-t border-slate-100 pt-5 sm:grid-cols-2"><NoteCard icon={<LockKeyhole size={16} />} title="Metadata stripping" body={report.metadata_stripped === false ? 'The export did not pass metadata verification.' : 'Export removes document metadata and page features as part of the server-side sanitization pass.'} /><NoteCard icon={<Trash2 size={16} />} title="Deletion note" body={report.deletion_notes || 'Delete the session when you are done. TTL cleanup is enabled server-side.'} /></div>
         {report.warnings.length ? <div className="mt-4 rounded-xl border border-warning/30 bg-warning/10 p-3 text-xs leading-5 text-amber-900"><p className="font-bold">Analysis warnings</p><ul className="mt-1 list-disc space-y-1 pl-4">{report.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></div> : null}
       </div>
     </section>
   )
}

function SummaryStat({ label, value, tone = 'navy' }: { label: string; value: number; tone?: 'navy' | 'cyan' | 'slate' }) {
  const colors = { navy: 'bg-ink text-white', cyan: 'bg-cyan/10 text-cyan-900', slate: 'bg-slate-100 text-slate-700' }
  return <div className={`rounded-2xl px-4 py-3 ${colors[tone]}`}><p className="text-[10px] font-bold uppercase tracking-[0.18em] opacity-70">{label}</p><p className="mt-1 text-2xl font-bold">{value}</p></div>
}

function CategoryList({ title, items, empty }: { title: string; items: [string, number][]; empty: string }) {
  return <div><p className="eyebrow">{title}</p><div className="mt-3 grid gap-2 sm:grid-cols-2">{items.length ? items.map(([kind, count]) => <div key={kind} className="flex items-center justify-between rounded-xl border border-slate-200 px-3 py-2.5"><span className="text-sm font-semibold text-navy">{humanizeKind(kind)}</span><span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-bold text-slate-600">{count}</span></div>) : <p className="text-sm text-slate-500">{empty}</p>}</div></div>
}

function VerificationBadge({ verification }: { verification: VerificationResponse }) {
  return <span className={`inline-flex items-center gap-2 rounded-full px-3 py-2 text-xs font-bold ${verification.passed ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'}`}>{verification.passed ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}{verification.passed ? 'Verification passed' : 'Verification needs review'}</span>
}

function VerificationItem({ label, passed }: { label: string; passed: boolean }) {
  return <div className="flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2.5 text-xs font-semibold text-slate-600"><span className={passed ? 'text-emerald-600' : 'text-rose-600'}>{passed ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}</span>{label}</div>
}

function NoteCard({ icon, title, body }: { icon: React.ReactNode; title: string; body: string }) {
  return <div className="flex items-start gap-3 rounded-2xl bg-slate-50 p-4"><span className="rounded-lg bg-white p-2 text-cyan shadow-sm">{icon}</span><div><p className="text-sm font-bold text-navy">{title}</p><p className="mt-1 text-xs leading-5 text-slate-500">{body}</p></div></div>
}

export default App
