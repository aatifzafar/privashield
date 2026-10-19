import type {
  AnalyzeRequest,
  ExportRequest,
  ExportResponse,
  HealthResponse,
  ReportResponse,
  UploadResponse,
} from '../types/api'

const configuredUrl = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')
const API_ROOT = configuredUrl.endsWith('/api') ? configuredUrl : `${configuredUrl}/api`

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

async function readError(response: Response): Promise<ApiError> {
  let detail = `Request failed with status ${response.status}`
  try {
    const payload = (await response.json()) as { detail?: string }
    if (payload.detail) detail = payload.detail
  } catch {
    // The server may return an empty or non-JSON error response.
  }
  return new ApiError(response.status, detail)
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_ROOT}${path}`, {
      ...init,
      headers: {
        Accept: 'application/json',
        ...(init?.headers || {}),
      },
    })
  } catch {
    throw new ApiError(0, 'The API could not be reached. Check VITE_API_URL and the backend status.')
  }

  if (!response.ok) throw await readError(response)
  return (await response.json()) as T
}

export const api = {
  root: API_ROOT,

  health(): Promise<HealthResponse> {
    return request<HealthResponse>('/health')
  },

  upload(file: File): Promise<UploadResponse> {
    const body = new FormData()
    body.append('file', file)
    return request<UploadResponse>('/upload', {
      method: 'POST',
      body,
      headers: {},
    })
  },

  analyze(input: AnalyzeRequest): Promise<ReportResponse> {
    return request<ReportResponse>('/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    })
  },

  report(sessionId: string): Promise<ReportResponse> {
    return request<ReportResponse>(`/report/${encodeURIComponent(sessionId)}`)
  },

  async export(input: ExportRequest): Promise<ExportResponse> {
    let response: Response
    try {
      response = await fetch(`${API_ROOT}/export`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/octet-stream' },
        body: JSON.stringify(input),
      })
    } catch {
      throw new ApiError(0, 'The API could not be reached while exporting. Check the backend status.')
    }
    if (!response.ok) throw await readError(response)

    const disposition = response.headers.get('Content-Disposition') || ''
    const filenameMatch = disposition.match(/filename="?([^";]+)"?/i)
    return {
      blob: await response.blob(),
      filename: filenameMatch?.[1] || 'privashield-redacted.pdf',
      sessionId: response.headers.get('X-Privashield-Session-ID'),
      exportId: response.headers.get('X-Privashield-Export-ID'),
      verification: response.headers.get('X-Privashield-Verification'),
    }
  },

  deleteSession(sessionId: string): Promise<{ deleted: boolean }> {
    return request<{ deleted: boolean }>(`/session/${encodeURIComponent(sessionId)}`, {
      method: 'DELETE',
    })
  },
}
