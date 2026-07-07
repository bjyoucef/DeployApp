/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/templates/**/*.html"],
  darkMode: ["class", '[data-theme="dark"]'],
  corePlugins: {
    preflight: false,
  },
  theme: {
    extend: {
      colors: {
        cis: {
          primary: "#450A54",
          secondary: "#4a148c",
        },
      },
      fontFamily: {
        sans: ["Segoe UI", "system-ui", "-apple-system", "sans-serif"],
      },
    },
  },
  plugins: [],
};
