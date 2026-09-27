/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          primary: "#4F46E5",
          secondary: "#7C3AED",
          warm: "#EA580C",
        },
        surface: {
          DEFAULT: "#FFFFFF",
          raised: "#F5F5F4",
          dark: "#1C1917",
          "dark-raised": "#292524",
        },
        importance: {
          critical: "#DC2626",
          high: "#EA580C",
          medium: "#CA8A04",
          low: "#6B7280",
        },
      },
      fontFamily: {
        sans: ["Geist", "Inter Variable", "system-ui", "sans-serif"],
        mono: ["Geist Mono", "JetBrains Mono", "monospace"],
      },
    },
  },
  plugins: [],
};
