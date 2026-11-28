export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  future: {
    hoverOnlyWhenSupported: true,
  },
  theme: {
    extend: {
      colors: {
        ink: "rgb(var(--bg-rgb) / <alpha-value>)",
        surface: "rgb(var(--surface-rgb) / <alpha-value>)",
        raised: "rgb(var(--raised-rgb) / <alpha-value>)",
        selected: "rgb(var(--selected-rgb) / <alpha-value>)",
        "selected-line": "rgb(var(--selected-border-rgb) / <alpha-value>)",
        line: "rgb(var(--border-rgb) / <alpha-value>)",
        mist: "rgb(var(--text-rgb) / <alpha-value>)",
        muted: "rgb(var(--muted-rgb) / <alpha-value>)",
        accent: "rgb(var(--accent-rgb) / <alpha-value>)",
        accentInk: "var(--accent-ink)",
        ok: "rgb(var(--ok-rgb) / <alpha-value>)",
        warn: "rgb(var(--warn-rgb) / <alpha-value>)",
        danger: "rgb(var(--danger-rgb) / <alpha-value>)",
        info: "rgb(var(--info-rgb) / <alpha-value>)",
      },
      fontFamily: {
        sans: ["Avenir Next", "Segoe UI", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SF Mono", "Cascadia Code", "Menlo", "monospace"],
      },
      fontSize: {
        xs: ["0.75rem", { lineHeight: "1rem" }],
        sm: ["0.8125rem", { lineHeight: "1.25rem" }],
        base: ["0.9375rem", { lineHeight: "1.5rem" }],
        lg: ["1.0625rem", { lineHeight: "1.375rem" }],
        xl: ["1.125rem", { lineHeight: "1.5rem" }],
        "2xl": ["1.5rem", { lineHeight: "1.875rem" }],
      },
      boxShadow: {
        menu: "0 8px 24px -12px rgb(0 0 0 / 0.45)",
        sticky: "0 -8px 24px -16px rgb(0 0 0 / 0.5)",
      },
      borderRadius: {
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
        xl: "var(--radius-xl)",
      },
      maxWidth: {
        shell: "90rem",
      },
    },
  },
  plugins: [],
};
