// Loaded through @config from frontend/tailwind.input.css.
// Source paths and runtime safelisting live in that CSS file for Tailwind v4.
module.exports = {
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
};
