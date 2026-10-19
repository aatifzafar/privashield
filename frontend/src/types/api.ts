export type DocumentType = 'pdf' | 'image'

export interface UploadResponse {
  session_id: string
  document_type: DocumentType
  pages: number
  max_pages: number
}

export interface AnalyzeRequest {
  session_id: string
  use_ocr?: boolean
}

export interface ExportRequest {
  session_id: string
  use_ocr?: boolean
  flatten_to_image?: boolean
  keep_last_n?: number | null
  retain_exports?: number | null
  findings?: FindingDecision[]
}

export interface FindingDecision {
  id: string
  page: number
  bbox: [number, number, number, number]
  decision: 'keep' | 'redact'
  manual?: boolean
}

export interface HealthResponse {
  status: string
  storage: string
}

export interface FindingResponse {
  id: string
  kind: string
  page: number
  bbox: [number, number, number, number]
  confidence: number
  source: string
  decision?: 'keep' | 'redact'
  manual?: boolean
}

export interface OcrResponse {
  requested: boolean
  available: boolean
  used: boolean
  message: string | null
}

export interface VerificationResponse {
  passed: boolean
  text_absent: boolean
  raw_bytes_absent: boolean
  metadata_clean: boolean
  annotations_clean: boolean
  ocr: string
  failures: string[]
  fields: FieldVerification[]
}

export interface FieldVerification {
  id: string
  kind: string
  passed: boolean
  text_absent: boolean
  raw_bytes_absent: boolean
  ocr: string
}

export interface ReportResponse {
  report_id: string
  session_id: string
  document_type: DocumentType
  pages: number
  findings: FindingResponse[]
  ocr: OcrResponse
  warnings: string[]
  verification: VerificationResponse | null
  created_at: string
  detected_count: number
  redacted_count: number
  kept_count: number
  redacted_categories: Record<string, number>
  kept_categories: Record<string, number>
  metadata_stripped: boolean | null
  deletion_notes: string
}

export interface ExportResponse {
  blob: Blob
  filename: string
  sessionId: string | null
  exportId: string | null
  verification: string | null
}
