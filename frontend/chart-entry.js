import Chart from "chart.js/auto";

// Preserve the app's existing Chart global while bundling the dependency locally.
window.Chart = Chart;
