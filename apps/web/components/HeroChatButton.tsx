"use client";
import { MessageCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useChatStore } from "@/stores/chat-store";

export function HeroChatButton() {
  const open = useChatStore((s) => s.open);
  return (
    <Button
      size="lg"
      onClick={open}
      className="bg-accent text-accent-foreground shadow-lg shadow-accent/20 hover:brightness-110"
    >
      <MessageCircle />
      Nhờ AI tư vấn
    </Button>
  );
}
