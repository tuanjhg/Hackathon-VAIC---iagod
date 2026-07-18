import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ChatWidget } from "@/components/ChatWidget";
import { useChatStore } from "@/stores/chat-store";

describe("ChatWidget", () => {
  beforeEach(() => {
    useChatStore.setState({ isOpen: false });
    useChatStore.getState().reset();
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

  it("reset button clears messages/context, starts a new session, and keeps the panel open", async () => {
    render(<ChatWidget />);
    fireEvent.click(screen.getByLabelText("Mở chatbot"));

    const initialSessionId = useChatStore.getState().sessionId;
    act(() => {
      useChatStore.getState().addMessage({ role: "user", content: "Phòng 18m2" });
      useChatStore
        .getState()
        .setContext({ budget_max: 15_000_000, room_area_m2: 18, priority: "em", xung_ho: null });
    });
    expect(useChatStore.getState().messages).toHaveLength(2);

    fireEvent.click(screen.getByLabelText("Bắt đầu lại hội thoại"));

    expect(useChatStore.getState().messages).toHaveLength(1);
    expect(useChatStore.getState().context).toEqual({
      budget_max: null,
      room_area_m2: null,
      priority: null,
      xung_ho: null,
    });
    expect(useChatStore.getState().sessionId).not.toBe(initialSessionId);
    expect(screen.getByLabelText("Chat tư vấn")).toBeInTheDocument();
  });

  it("advisor contact modal opens from the trigger and closes via the X button or backdrop", () => {
    render(<ChatWidget />);
    fireEvent.click(screen.getByLabelText("Mở chatbot"));

    fireEvent.click(screen.getByText("Cần hỗ trợ thêm? Gặp tư vấn viên"));
    const modal = screen.getByLabelText("Gặp tư vấn viên");
    expect(modal).toBeInTheDocument();
    const callLink = screen.getByRole("link", { name: /Gọi 1900 1234/ });
    expect(callLink).toHaveAttribute("href", "tel:19001234");

    fireEvent.click(screen.getByLabelText("Đóng"));
    expect(screen.queryByLabelText("Gặp tư vấn viên")).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("Cần hỗ trợ thêm? Gặp tư vấn viên"));
    expect(screen.getByLabelText("Gặp tư vấn viên")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Gặp tư vấn viên").parentElement as HTMLElement);
    expect(screen.queryByLabelText("Gặp tư vấn viên")).not.toBeInTheDocument();
  });
});
