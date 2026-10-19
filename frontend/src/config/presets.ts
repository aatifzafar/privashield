export type PurposePreset = {
  id: string
  label: string
  description: string
  focus: string[]
  keepKinds: string[]
  maskKinds: string[]
  maskLastN?: number
}

/** Data-driven defaults only; every decision remains editable after analysis. */
export const PURPOSE_PRESETS: PurposePreset[] = [
  {
    id: 'identity',
    label: 'Identity verification',
    description: 'Keep the name and show only the last four characters of common ID numbers.',
    focus: ['Name', 'Last 4 of ID', 'Review DOB, address, phone, photo, QR'],
    keepKinds: ['name_label'],
    maskKinds: ['pan', 'aadhaar', 'passport'],
    maskLastN: 4,
  },
  {
    id: 'address',
    label: 'Address verification',
    description: 'Keep the name and address while removing identity numbers and contact details.',
    focus: ['Name', 'Address', 'Redact IDs, DOB, photo'],
    keepKinds: ['name_label', 'address_label'],
    maskKinds: [],
  },
  {
    id: 'organization',
    label: 'Share with organization',
    description: 'Keep only the name for a minimal external handoff.',
    focus: ['Name only', 'Redact all other detections'],
    keepKinds: ['name_label'],
    maskKinds: [],
  },
]

export function presetDecision(preset: PurposePreset, kind: string): 'keep' | 'redact' {
  return preset.keepKinds.includes(kind) ? 'keep' : 'redact'
}

export function presetMaskLastN(preset: PurposePreset, kind: string): number | undefined {
  return preset.maskKinds.includes(kind) ? preset.maskLastN : undefined
}
