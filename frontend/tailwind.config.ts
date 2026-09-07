import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          950: "#FFFFFF",
          900: "#F0F2F5",
          850: "#E4E6EB",
          800: "#D8DADF"
        },
        line: "#CED0D4",
        "line-subtle": "#E4E6EB",
        ink: "#1C1E21",
        muted: "#65676B",
        faint: "#8A8D91",
        brand: {
          action: "#1877F2",
          hover: "#166FE5",
          soft: "#E7F3FF"
        },
        danger: {
          action: "#FA383E",
          soft: "#FDE7E9"
        },
        success: "#42B72A",
        warning: "#d3a04d"
      },
      borderRadius: {
        sm: "6px",
        md: "8px",
        lg: "12px"
      },
      boxShadow: {
        panel: "0 18px 60px rgba(0, 0, 0, 0.12)"
      }
    }
  },
  plugins: []
};

export default config;