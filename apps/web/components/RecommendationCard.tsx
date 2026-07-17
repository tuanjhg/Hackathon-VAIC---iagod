import Link from "next/link";
import { CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatPrice } from "@/lib/utils";
import type { Recommendation } from "@/types";

export function RecommendationCard({ item }: { item: Recommendation }) { return <div className="rounded-xl border border-brand-100 bg-brand-50 p-3"><div className="flex items-start justify-between gap-2"><span className="rounded-full bg-brand-600 px-2 py-1 text-[10px] font-bold text-white">{item.label}</span><span className="text-sm font-black text-emerald-600">{item.match_score}%</span></div><p className="mt-2 text-sm font-bold">{item.product.name}</p><p className="mt-1 font-black text-red-600">{formatPrice(item.product.sale_price)}</p><p className="mt-2 text-xs leading-5 text-slate-600">{item.reason}</p><div className="mt-2 grid gap-1">{item.strengths.slice(0, 2).map((value) => <span key={value} className="flex gap-1 text-xs"><CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-500"/>{value}</span>)}</div><p className="mt-2 text-xs text-amber-700"><strong>Đánh đổi:</strong> {item.trade_off}</p><Button asChild size="sm" className="mt-3 w-full"><Link href={`/products/${item.product.slug}`}>Xem chi tiết</Link></Button></div>; }

