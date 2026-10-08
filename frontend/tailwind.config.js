/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{js,ts,jsx,tsx}", "./components/**/*.{js,ts,jsx,tsx}"],
  darkMode: ["class"],
  theme: {
    extend: {
      colors: {
        hive: {
          bg: "#1a1423",
          panel: "#2a2139",
          amber: "#ffc93c",
          amberDark: "#e0a100",
          honey: "#ff9f1c",
          ink: "#0d0a14",
          mint: "#5bd1a6",
          danger: "#ff5d5d",
          line: "#4a3f63",
        },
      },
      fontFamily: {
        pixel: ["\"Press Start 2P\"", "monospace"],
      },
      boxShadow: {
        pixel: "4px 4px 0 0 #0d0a14",
      },
    },
  },
  plugins: [],
};
