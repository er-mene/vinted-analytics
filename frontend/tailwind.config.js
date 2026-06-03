/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        cream: "#f3efe7",
        panel: "#fffaf3",
        ink: "#1f2937",
        muted: "#6b7280",
        accent: "#b45309",
        "accent-2": "#0f766e",
        line: "#e5dccf",
        green: "#059669",
        red: "#dc2626",
        yellow: "#d97706",
      },
      fontFamily: {
        serif: ['Georgia', '"Times New Roman"', 'serif'],
        sans: ['"Helvetica Neue"', 'Arial', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
