/** @type {import('tailwindcss').Config} */
// The RIE design language: an institutional ledger. Deep ink chrome, a warm paper canvas,
// hairline rules, one verdigris accent, and IBM Plex for a typeset, regulatory feel.
// `slate` is re-pointed at the same ink-to-paper scale so pages not yet rebuilt on the
// design system still sit in the palette.
const ink = {
  50: "#F6F5F1", 100: "#EFEDE7", 200: "#E3DFD5", 300: "#CFC9BB", 400: "#959CA6",
  500: "#68727F", 600: "#48535F", 700: "#2F3D4D", 800: "#18293B", 900: "#0B1F33", 950: "#071421",
};
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink,
        paper: "#F4F2EC",
        line: { DEFAULT: "#E3DFD5", strong: "#CFC9BB" },
        brand: { 50: "#E8F4F2", 100: "#CDE7E3", 200: "#9FD0C9", 500: "#12807A", 600: "#0E6A65", 700: "#0B5450" },
        ok: { bg: "#E5F3EA", line: "#B5DCC3", fg: "#1A6B41" },
        warn: { bg: "#FBF0D9", line: "#EDD49A", fg: "#8A5A00" },
        bad: { bg: "#FBE8E5", line: "#F0BDB6", fg: "#A8261D" },
        info: { bg: "#E6EEF8", line: "#BCD0EA", fg: "#1D4C86" },
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      boxShadow: {
        panel: "0 1px 0 rgba(11,31,51,0.04)",
        pop: "0 12px 32px -8px rgba(11,31,51,0.28), 0 2px 6px rgba(11,31,51,0.10)",
      },
      keyframes: {
        rise: { from: { opacity: "0", transform: "translateY(6px)" }, to: { opacity: "1", transform: "none" } },
        fade: { from: { opacity: "0" }, to: { opacity: "1" } },
      },
      animation: { rise: "rise 220ms cubic-bezier(.2,.7,.2,1) both", fade: "fade 160ms ease-out both" },
    },
  },
  plugins: [],
};
