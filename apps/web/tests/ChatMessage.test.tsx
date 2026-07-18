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
    expect(screen.getByText("Nội dung đã qua bước đối chiếu dữ liệu.")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Nguồn dữ liệu (1)"));
    expect(screen.getByText(/sku-good/)).toBeInTheDocument();
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
