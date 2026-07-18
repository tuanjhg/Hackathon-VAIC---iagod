export interface Promotion { title: string; description: string }

export interface Product {
  id: number;
  sku: string;
  slug: string;
  name: string;
  brand: string;
  category: string;
  category_slug: string;
  original_price: string;
  sale_price: string;
  currency: string;
  capacity_btu: number;
  horsepower: number;
  recommended_area_min: number;
  recommended_area_max: number;
  inverter: boolean;
  noise_db: number | null;
  energy_rating: string;
  warranty_months: number;
  stock_status: "in_stock" | "low_stock" | "out_of_stock" | "unknown";
  stock_quantity: number;
  promotion: Promotion | null;
  short_description: string;
  image_url: string;
  rating: number;
  review_count: number;
  featured: boolean;
  specifications: Record<string, unknown>;
}

export interface ProductPage { items: Product[]; total: number; page: number; page_size: number; pages: number }
export interface Category { id: number; name: string; slug: string }
export interface ProductFilters { search?: string; category?: string; brand?: string; min_price?: number; max_price?: number; room_area?: number; inverter?: boolean; in_stock?: boolean; sort?: string; page?: number; page_size?: number }
export interface Comparison { products: Product[]; best_price_id: number | null; quietest_id: number | null; best_overall_id: number | null }
export interface NeedProfile {
  category: string | null;
  slots: Record<string, unknown>;
  asked_slots: string[];
  clarify_rounds: number;
  assumptions: string[];
}
export interface ChatContext { budget_max: number | null; room_area_m2: number | null; priority: string | null; need_profile?: NeedProfile | null }
export interface Recommendation { product: Product; label: string; match_score: number; reason: string; strengths: string[]; trade_off: string }
// AI-pipeline card: rendered straight from the S5 candidate JSON (ADR C5).
export interface AdvisorCard {
  sku: string;
  product_slug: string | null;
  name: string;
  label: string;
  match_score: number;
  price: number | null;
  image_url: string | null;
  specs: Record<string, unknown>;
  reason: string;
  strengths: string[];
  trade_off: string;
  missing_fields: string[];
}
export interface AdvisorAntiPick { sku: string; name: string; reason: string | null }
export interface SourcePanelEntry { sku: string; field: string; dataset: string; fetched_at: string | null }
export interface VerifierFlag { action: "corrected" | "removed"; sku: string | null; field: string | null; claimed_value: number | null; actual_value: number | null }
export type GuardrailStatus = "verified" | "corrected" | "grounded_fallback" | "limited" | "not_applicable" | "unavailable";
export interface GuardrailMeta {
  status: GuardrailStatus;
  label: string;
  source_count: number;
  corrected_claims: number;
  omitted_claims: number;
  missing_data_count: number;
  notices: string[];
}
export type ActionKind = "quick_reply" | "category" | "prompt" | "retry" | "link";
export interface SelectedAction { id: string; value: string; slot_name?: string | null }
export interface ResponseAction extends SelectedAction {
  kind: ActionKind;
  label: string;
  url?: string | null;
}
export type ChatResponseType =
  | "follow_up"
  | "clarification"
  | "recommendations"
  | "policy"
  | "no_results"
  | "handoff"
  | "out_of_scope"
  | "unsupported"
  | "error";
export interface ChatResponse {
  response_type: ChatResponseType;
  intent?: string | null;
  message: string;
  quick_replies: string[];
  actions: ResponseAction[];
  recommendations: Recommendation[];
  cards?: AdvisorCard[];
  anti_pick?: AdvisorAntiPick | null;
  source_panel?: SourcePanelEntry[];
  verifier_flags?: VerifierFlag[];
  guardrail: GuardrailMeta;
  context: ChatContext;
}
// SSE events emitted by POST /chat/messages with Accept: text/event-stream.
export type ChatStreamEvent =
  | { type: "delta"; text: string }
  | { type: "final"; response: ChatResponse };
