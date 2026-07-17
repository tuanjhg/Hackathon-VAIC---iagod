import { ProductsBrowser } from "@/components/ProductsBrowser";
export default async function ProductsPage({ searchParams }: { searchParams: Promise<{ search?: string }> }) { const params = await searchParams; return <div className="container py-10"><p className="font-bold text-brand-600">CATALOG</p><h1 className="mt-2 text-3xl font-black">Máy lạnh cho mọi không gian</h1><p className="mt-3 text-slate-600">Dữ liệu giá, tồn kho và thông số được cung cấp từ backend API.</p><div className="mt-8"><ProductsBrowser initialSearch={params.search}/></div></div>; }

