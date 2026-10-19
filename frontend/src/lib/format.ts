export const KIND_LABELS: Record<string, string> = {
  aadhaar: 'Aadhaar number',
  address_label: 'Address',
  bank_account: 'Bank account',
  date_of_birth: 'Date of birth',
  email: 'Email address',
  face: 'Face',
  ifsc: 'IFSC code',
  indian_phone: 'Phone number',
  indian_pin: 'PIN code',
  name_label: 'Name',
  pan: 'PAN number',
  passport: 'Passport number',
  qr: 'QR code',
}

export function humanizeKind(kind: string): string {
  if (KIND_LABELS[kind]) return KIND_LABELS[kind]
  return kind
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function confidencePercent(value: number): string {
  return `${Math.round(value * 100)}%`
}

export function confidenceTone(value: number): 'high' | 'medium' | 'low' {
  if (value >= 0.9) return 'high'
  if (value >= 0.8) return 'medium'
  return 'low'
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function downloadJson(value: unknown, filename: string): void {
  const blob = new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' })
  downloadBlob(blob, filename)
}
