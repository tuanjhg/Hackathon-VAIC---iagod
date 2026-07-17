import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva("inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl text-sm font-semibold transition-colors disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500", { variants: { variant: { default: "bg-brand-600 text-white hover:bg-brand-700", outline: "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50", ghost: "text-slate-700 hover:bg-slate-100", danger: "bg-red-50 text-red-700 hover:bg-red-100" }, size: { default: "h-10 px-4", sm: "h-9 px-3", lg: "h-12 px-6" } }, defaultVariants: { variant: "default", size: "default" } });

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> { asChild?: boolean }
export function Button({ className, variant, size, asChild = false, ...props }: ButtonProps) { const Comp = asChild ? Slot : "button"; return <Comp className={cn(buttonVariants({ variant, size, className }))} {...props} />; }

