export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        ink: "var(--bg)",
        surface: "var(--surface)",
        raised: "var(--raised)",
        line: "var(--border)",
        mist: "var(--text)",
        muted: "var(--muted)",
        accent: "var(--accent)",
        accentInk: "var(--accent-ink)",
        ok: "var(--ok)",
        warn: "var(--warn)",
        danger: "var(--danger)",
        info: "var(--info)",
      },
      fontFamily: {
        sans: ["Avenir Next", "Segoe UI", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SF Mono", "Cascadia Code", "Menlo", "monospace"],
      },
      borderRadius: {
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
        xl: "var(--radius-xl)",
      },
      maxWidth: {
        shell: "112.5rem",
      },
    },
  },
  plugins: [],
};
