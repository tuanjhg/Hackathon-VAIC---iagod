import { HeroBanners } from "@/components/home/HeroBanners";
import { TrustBar } from "@/components/home/TrustBar";
import { PromoGrid } from "@/components/home/PromoGrid";
import { FlashSale } from "@/components/home/FlashSale";
import { ShopByNeed } from "@/components/home/ShopByNeed";
import { AdvisorBand } from "@/components/home/AdvisorBand";
import { SubBanners } from "@/components/home/SubBanners";
import { SectionHeader } from "@/components/home/SectionHeader";
import { PromoRail } from "@/components/home/PromoRail";
import { ProductGrid } from "@/components/ProductGrid";
import { Reveal } from "@/components/ui/reveal";
import { Snowflake } from "lucide-react";

export default function HomePage() {
  return (
    <div className="pb-4">
      <HeroBanners />

      <Reveal>
        <TrustBar />
      </Reveal>

      <Reveal>
        <PromoGrid />
      </Reveal>

      <FlashSale />

      <Reveal>
        <ShopByNeed />
      </Reveal>

      <Reveal>
        <section className="container pt-12">
          <SectionHeader eyebrow="ĐƯỢC QUAN TÂM" title="Sản phẩm nổi bật" href="/products" />
          <div className="mt-6">
            <ProductGrid filters={{ sort: "featured" }} limit={6} />
          </div>
        </section>
      </Reveal>

      <AdvisorBand />

      <Reveal>
        <SubBanners />
      </Reveal>

      <Reveal>
        <PromoRail
          icon={<Snowflake className="h-5 w-5 text-brand-100" />}
          title="Trạm giá tốt trong tuần"
          viewAllHref="/products?sort=price_asc"
          filters={{ sort: "price_asc" }}
          limit={10}
          banner={{
            title: "Sale mạnh giải nhiệt",
            subtitle: "Trả chậm 0% · miễn phí công lắp · voucher đến 1 triệu",
            cta: "XEM NGAY",
            href: "/products?sort=price_asc",
            tone: "from-brand-800 via-brand-600 to-accent",
          }}
        />
      </Reveal>
    </div>
  );
}
