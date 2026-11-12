export type Identifier = { type: string; value: string }
export type TextSample = { text: string; posted_at: string }
export type Persona = { persona_id: string; marketplace: string; handle: string; identifiers: Identifier[]; texts: TextSample[]; first_seen: string; last_seen: string }
export type Evidence = { kind: string; description: string }
export type Comparison = { confidence: number; raw_confidence: number; single_signal: boolean; tier: 'strong'|'moderate'|'weak'|'lead'; breakdown: Record<string, number>; evidence: Record<string, Evidence[]>; explanation: string; explanation_source: string; explanation_label: string }
export type Candidate = Comparison & { persona: Persona }
