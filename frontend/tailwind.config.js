/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eff6ff",
          100: "#dbeafe",
          300: "#a5b4fc",
          400: "#818cf8",
          500: "#6366f1",
          600: "#4f46e5",
          700: "#4338ca",
        },
        studio: {
          cyan: "#06b6d4",
          indigo: "#6366f1",
          emerald: "#10b981",
          amber: "#f59e0b",
          rose: "#f43f5e",
        },
        dark: {
          bg: "#09090b",
          surface: "#111217",
          card: "#14151b",
          hover: "#1e1f29",
          border: "#262733",
          muted: "#94a3b8",
          text: "#f8fafc"
        },
        light: {
          bg: "#f8fafc",
          surface: "#ffffff",
          card: "#ffffff",
          hover: "#f1f5f9",
          border: "#e2e8f0",
          muted: "#64748b",
          text: "#0f172a"
        }
      },
      fontFamily: {
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          "Consolas",
          "Liberation Mono",
          "Courier New",
          "monospace"
        ]
      }
    },
  },
  plugins: [],
}
