"use client";
import { MessageCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useChatStore } from "@/stores/chat-store";
export function HeroChatButton() { const open = useChatStore((state) => state.open); return <Button size="lg" onClick={open}><MessageCircle/>Nhờ AI tư vấn</Button>; }

