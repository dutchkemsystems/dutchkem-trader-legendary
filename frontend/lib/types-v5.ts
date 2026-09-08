export interface MLPrediction {
  p_up: number;
  direction: string;
  model_name: string;
  features_used: number;
}

export interface GateStatus {
  trade_allowed: boolean;
  gates: Record<string, { passed: boolean; value: number | string; reason: string }>;
  passed_count: number;
  total_gates: number;
}

export interface DebateResult {
  symbol: string;
  winner: string;
  bull_confidence: number;
  bear_confidence: number;
  rounds: number;
  error?: string;
}

export interface MemorySituation {
  symbol: string;
  situation: string;
  outcome: string;
  lesson: string;
  relevance_score: number;
}

export interface FullConsensusResult {
  action: string;
  confidence: number;
  agreement_pct: number;
  reason: string;
  votes: Record<string, number>;
  debate?: DebateResult;
  similar_situations?: MemorySituation[];
  gates?: GateStatus;
}
