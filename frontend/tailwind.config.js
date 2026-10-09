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
          500: "#3b82f6",
          600: "#2563eb",
          700: "#1d4ed8",
        },
        dark: {
          bg: "#0a0d14",
          card: "#111726",
          hover: "#182135",
          border: "#202b40",
          muted: "#8a9ab2",
          text: "#f1f5f9"
        }
      }
    },
  },
  plugins: [],
}
