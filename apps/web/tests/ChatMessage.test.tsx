import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AdvisorCard } from "@/components/AdvisorCard";
import { ChatMessage } from "@/components/ChatMessage";

describe("business response rendering", () => {
  it("shows anti-pick, verification state and source provenance", () => {
    render(
      <ChatMessage
        onQuickReply={vi.fn()}
        message={{
          role: "assistant",
          content: "Dạ đây là các lựa chọn phù hợp ạ.",
          responseType: "recommendations",
          antiPick: { sku: "sku-bad", name: "Mẫu không phù hợp", reason: "Vượt ngân sách" },
          verifierFlags: [],
          guardrail: {
            status: "verified",
            label: "Đã đối chiếu dữ liệu nguồn",
            source_count: 1,
            corrected_claims: 0,
            omitted_claims: 0,
            missing_data_count: 0,
            notices: [],
          },
          sourcePanel: [
            {
              sku: "sku-good",
              field: "price",
              dataset: "catalog",
              fetched_at: "2026-07-18T09:00:00Z",
            },
          ],
        }}
      />,
    );

    expect(screen.getByText("Không nên chọn trong nhu cầu này")).toBeInTheDocument();
    expect(screen.getByText("Vượt ngân sách")).toBeInTheDocument();
    expect(screen.getByText("Đã đối chiếu dữ liệu nguồn")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Nguồn dữ liệu · 1 sản phẩm"));
    expect(screen.getByText(/sku-good/)).toBeInTheDocument();
    expect(screen.getByText(/Giá bán/)).toBeInTheDocument();
  });

  it("renders canonical action labels and sends the structured action", () => {
    const onQuickReply = vi.fn();
    const action = {
      id: "slot:quy_mo:ba_bon",
      kind: "quick_reply" as const,
      label: "3–4 người",
      value: "ba_bon",
      slot_name: "quy_mo",
    };
    render(
      <ChatMessage
        onQuickReply={onQuickReply}
        message={{ role: "assistant", content: "Nhà mình có mấy người?", actions: [action] }}
      />,
    );

    fireEvent.click(screen.getByText("3–4 người"));
    expect(onQuickReply).toHaveBeenCalledWith("3–4 người", action);
  });

  it("labels grounded fallback without claiming full verification", () => {
    const { container } = render(
      <ChatMessage
        onQuickReply={vi.fn()}
        message={{
          role: "assistant",
          content: "Dữ liệu trực tiếp",
          responseType: "recommendations",
          guardrail: {
            status: "grounded_fallback",
            label: "Đang hiển thị dữ liệu nguồn trực tiếp",
            source_count: 2,
            corrected_claims: 0,
            omitted_claims: 0,
            missing_data_count: 0,
            notices: [],
          },
        }}
      />,
    );

    expect(screen.getByText("Đang hiển thị dữ liệu nguồn trực tiếp")).toBeInTheDocument();
    expect(container).not.toHaveTextContent("Đã đối chiếu dữ liệu nguồn");
  });

  it("labels a transaction handoff explicitly", () => {
    render(
      <ChatMessage
        onQuickReply={vi.fn()}
        message={{
          role: "assistant",
          content: "Vui lòng liên hệ chăm sóc khách hàng.",
          responseType: "handoff",
        }}
      />,
    );

    expect(screen.getByText("Cần kênh hỗ trợ chính thức")).toBeInTheDocument();
  });

  it("never presents missing product data as an estimate", () => {
    render(
      <AdvisorCard
        item={{
          sku: "sku-1",
          product_slug: "san-pham-1",
          name: "Sản phẩm 1",
          label: "Lựa chọn cân bằng",
          match_score: 85,
          price: null,
          image_url: null,
          specs: {},
          reason: "Phù hợp nhu cầu.",
          strengths: ["Chạy êm"],
          trade_off: "Giá cao hơn lựa chọn khác",
          missing_fields: ["độ ồn"],
        }}
      />,
    );

    expect(screen.getByText("Chưa có dữ liệu giá trực tuyến")).toBeInTheDocument();
    expect(screen.getByText(/Hệ thống không tự ước lượng/)).toBeInTheDocument();
    expect(screen.queryByText(/ước lượng tự động/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Xem chi tiết" })).toHaveAttribute(
      "href",
      "/products/san-pham-1",
    );
  });
});
