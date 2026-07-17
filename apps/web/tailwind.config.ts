import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: { brand: { 50: "#eff8ff", 100: "#dbefff", 500: "#1683e6", 600: "#0869c2", 700: "#07549a", 900: "#0b3458" } },
      boxShadow: { card: "0 10px 30px rgba(9, 70, 120, 0.08)" },
    },
  },
  plugins: [],
} satisfies Config;

