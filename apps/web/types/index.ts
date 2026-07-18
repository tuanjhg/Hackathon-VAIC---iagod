export interface Promotion { title: string; description: string }

export interface Product {
  id: number;
  sku: string;
  slug: string;
  name: string;
  brand: string;
  category: string;
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
}

export interface ProductPage { items: Product[]; total: number; page: number; page_size: number; pages: number }
export interface ProductFilters { search?: string; brand?: string; min_price?: number; max_price?: number; room_area?: number; inverter?: boolean; in_stock?: boolean; sort?: string; page?: number; page_size?: number }
export interface Comparison { products: Product[]; best_price_id: number | null; quietest_id: number | null; best_overall_id: number | null }
export interface ChatContext { budget_max: number | null; room_area_m2: number | null; priority: string | null; xung_ho: string | null }
export interface Recommendation { product: Product; label: string; match_score: number; reason: string; strengths: string[]; trade_off: string }
export interface ChatResponse { response_type: "follow_up" | "recommendations"; message: string; quick_replies: string[]; recommendations: Recommendation[]; context: ChatContext }
