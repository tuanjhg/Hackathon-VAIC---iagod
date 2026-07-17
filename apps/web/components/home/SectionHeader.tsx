import Link from "next/link";

export function SectionHeader({
  eyebrow,
  title,
  href,
  linkLabel = "Xem tất cả →",
}: {
  eyebrow: string;
  title: string;
  href?: string;
  linkLabel?: string;
}) {
  return (
    <div className="flex items-end justify-between gap-4">
      <div>
        <p className="font-bold text-primary">{eyebrow}</p>
        <h2 className="mt-1 font-heading text-2xl font-extrabold sm:text-3xl">{title}</h2>
      </div>
      {href && (
        <Link href={href} className="shrink-0 text-sm font-bold text-primary hover:underline">
          {linkLabel}
        </Link>
      )}
    </div>
  );
}
