import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          950: "#11110f",
          900: "#171714",
          850: "#1d1d19",
          800: "#24231f"
        },
        line: "#2b2a25",
        "line-subtle": "#23231f",
        ink: "#f3f0e8",
        muted: "#aaa69a",
        faint: "#77746b",
        amber: {
          action: "#d48a31",
          hover: "#e49a3f",
          soft: "#2b2115"
        },
        danger: {
          action: "#c96b62",
          soft: "#2a1714"
        },
        success: "#65a67b",
        warning: "#d3a04d"
      },
      borderRadius: {
        sm: "6px",
        md: "8px",
        lg: "12px"
      },
      boxShadow: {
        panel: "0 18px 60px rgba(0, 0, 0, 0.32)"
      }
    }
  },
  plugins: []
};

export default config;