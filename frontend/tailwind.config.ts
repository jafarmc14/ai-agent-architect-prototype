import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          950: "#090c10",
          900: "#0d1117",
          850: "#11161d",
          800: "#151b23",
          750: "#1b222c"
        },
        line: "#2b3441",
        ink: "#f2f5f8",
        muted: "#97a3b3",
        amber: {
          action: "#ff8a00",
          deep: "#b86900"
        },
        danger: {
          action: "#ff3038",
          soft: "#321318"
        }
      },
      boxShadow: {
        panel: "0 18px 60px rgba(0, 0, 0, 0.24)"
      }
    }
  },
  plugins: []
};

export default config;
