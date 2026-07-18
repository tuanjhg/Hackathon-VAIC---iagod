import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ChatWidget } from "@/components/ChatWidget";
import { useChatStore } from "@/stores/chat-store";

describe("ChatWidget", () => {
  beforeEach(() => {
    useChatStore.getState().resetChat();
    useChatStore.setState({ isOpen: false });
  });

  it("opens, updates messages and closes without treating scroll result as cleanup", async () => {
    const scrollIntoView = vi.fn(() => ({ cancel: vi.fn() }));
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoView,
    });

    render(<ChatWidget/>);
    fireEvent.click(screen.getByLabelText("Mở chatbot"));
    expect(screen.getByLabelText("Chat tư vấn")).toBeInTheDocument();
    expect(screen.getByText("Đồng ý và bắt đầu")).toBeInTheDocument();
    expect(screen.getByLabelText("Tin nhắn")).toBeDisabled();

    fireEvent.click(screen.getByText("Đồng ý và bắt đầu"));
    expect(screen.getByLabelText("Tin nhắn")).toBeEnabled();

    act(() => {
      useChatStore.getState().addMessage({ role: "assistant", content: "Tin nhắn mới" });
    });
    expect(scrollIntoView).toHaveBeenCalled();

    fireEvent.click(screen.getByLabelText("Đóng chatbot"));
    // Panel unmounts after the AnimatePresence exit transition.
    await waitFor(() =>
      expect(screen.queryByLabelText("Chat tư vấn")).not.toBeInTheDocument(),
    );
  });
});
