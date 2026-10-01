module.exports = {
  content: ["./frontend/index.html", "./frontend/app.js", "./frontend/c2-pwa.js"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Outfit Variable", "sans-serif"],
        heading: ["Plus Jakarta Sans Variable", "sans-serif"],
      },
      transitionTimingFunction: {
        spring: "cubic-bezier(0.175, 0.885, 0.32, 1.275)",
        smooth: "cubic-bezier(0.25, 1, 0.5, 1)",
      },
      scale: {
        98: "0.98",
      },
    },
  },
  safelist: [
    "hidden",
    "badge-low",
    "badge-mod",
    "badge-high",
    "badge-pulse",
    "led-green",
    "led-amber",
    "led-red",
    "toast-success",
    "toast-error",
    "toast-warning",
    "toast-info",
  ],
};
