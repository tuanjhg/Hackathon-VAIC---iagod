# NeedWise Copilot — Design System (MASTER)

> Nguồn chân lý (Source of Truth) cho toàn bộ giao diện web. Mọi trang bám theo file này.
> Hướng: **Trust-tech** — xanh dương tin cậy + teal/cyan gợi cảm giác "mát/làm lạnh" cho ngành máy lạnh.
> Stack: Next.js 15 (App Router) · React 19 · Tailwind 3 · CSS variables (light + dark) · Framer Motion.

## 1. Nguyên tắc

- **Token-driven**: không hardcode hex trong component. Dùng semantic token (`bg-primary`, `text-muted-foreground`, `border-border`…).
- **Light + Dark** đồng hạng: mọi token có giá trị ở cả 2 theme, test contrast riêng.
- **Accessible**: text ≥ 4.5:1, focus ring rõ, tôn trọng `prefers-reduced-motion`, target bấm ≥ 40px.
- **Không bịa dữ liệu**: field thiếu hiển thị "Chưa có dữ liệu", không suy đoán.
- **Ảnh**: hiện dùng placeholder → layout ratio cố định (4/3) + skeleton, không vỡ khi ảnh lỗi.

## 2. Màu (semantic tokens — định nghĩa dạng RGB channel trong `globals.css`)

| Token | Light | Dark | Dùng cho |
|---|---|---|---|
| `background` | `#F8FAFC` | `#0B1220` | Nền trang |
| `foreground` | `#0F172A` | `#E2E8F0` | Text chính |
| `card` | `#FFFFFF` | `#111A2E` | Bề mặt card |
| `muted` | `#F1F5F9` | `#1A2740` | Nền phụ |
| `muted-foreground` | `#64748B` | `#94A3B8` | Text phụ |
| `border` / `input` | `#E2E8F0` | `#1E2A44` | Viền, divider |
| `primary` | `#2563EB` | `#3B82F6` | Nút chính, link, brand |
| `accent` | `#06B6D4` | `#22D3EE` | Nhấn "mát", tiết kiệm điện |
| `success` | `#059669` | `#34D399` | Còn hàng, eco |
| `destructive` | `#DC2626` | `#F87171` | Hết hàng, xóa, giá sale |
| `ring` | `#2563EB` | `#3B82F6` | Focus ring |

**Brand scale** (tĩnh, cho gradient/hero): `brand-50 #EFF6FF … 500 #3B82F6 · 600 #2563EB · 700 #1D4ED8 · 900 #1E3A8A`.

## 3. Typography

- **Heading**: Be Vietnam Pro (500/600/700/800) — `font-heading`. Thiết kế riêng cho tiếng Việt (dấu chuẩn, crisp).
- **Body**: Nunito Sans (400/500/600/700) — mặc định `font-sans`.
- Nạp qua **next/font** (self-host, không `@import` → tránh layout shift).
- Scale: display `text-4xl/5xl font-heading font-extrabold` · h2 `text-3xl font-heading font-bold` · body `text-base leading-7`.

## 4. Hình khối & hiệu ứng

- **Radius**: `--radius: 0.875rem` (card `rounded-2xl`, control `rounded-xl`, pill `rounded-full`).
- **Shadow**: `shadow-card` (mềm, xanh nhạt) cho card; elevation tăng khi hover.
- **Hover**: đổi màu/elevation 150–300ms, **không** dịch layout gây jitter (dùng transform nhẹ + shadow).
- **Motion**: Framer Motion — fade/slide 150–300ms, stagger nhẹ cho grid & chat. Bọc bằng check `prefers-reduced-motion`.

## 5. Spacing & layout

- Rhythm 4/8px. Section dọc: 16/24/32/48/64.
- `.container`: `min(1180px, 100% - 32px)`, gutter tăng theo breakpoint.
- Breakpoint kiểm thử: **375 / 768 / 1024 / 1440**.

## 6. Component primitives (`components/ui/`)

`Button` · `Input` · `Select` · `Card` · `Badge` · `Skeleton` · `Dialog/Sheet` (radix). Tất cả token-driven, có trạng thái hover/focus/disabled ở cả 2 theme.

## 7. Checklist trước khi giao (web-adapted)

- [ ] Icon vector (lucide) đồng bộ stroke, không dùng emoji làm icon.
- [ ] `cursor-pointer` + hover transition 150–300ms trên mọi phần tử bấm được.
- [ ] Text 4.5:1 ở **cả** light và dark; secondary ≥ 3:1.
- [ ] Focus ring nhìn thấy cho keyboard nav; thứ tự focus khớp thị giác.
- [ ] `prefers-reduced-motion` được tôn trọng.
- [ ] Responsive 375/768/1024/1440, không tràn ngang.
- [ ] Trạng thái rỗng/loading (skeleton)/lỗi đều có thiết kế.

## 8. Overrides theo trang

Đặt tại `design-system/pages/<page>.md` khi một trang cần lệch khỏi MASTER (vd chatbot có motion đậm hơn). Không có file override → dùng MASTER.
