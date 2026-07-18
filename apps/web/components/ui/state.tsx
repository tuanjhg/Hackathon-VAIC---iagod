import { cn } from "@/lib/utils";

/** Shared empty / error container (replaces the old .state-box class). */
export function StateBox({
  icon,
  title,
  description,
  action,
  tone = "muted",
  className,
}: {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
  tone?: "muted" | "danger";
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex min-h-64 flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-border bg-card/50 p-8 text-center",
        className,
      )}
    >
      {icon && (
        <span
          className={cn(
            "grid h-12 w-12 place-items-center rounded-2xl",
            tone === "danger" ? "bg-destructive/10 text-destructive" : "bg-muted text-muted-foreground",
          )}
        >
          {icon}
        </span>
      )}
      <p className={cn("font-heading font-bold", tone === "danger" ? "text-destructive" : "text-foreground")}>
        {title}
      </p>
      {description && <p className="max-w-sm text-sm text-muted-foreground">{description}</p>}
      {action}
    </div>
  );
}
