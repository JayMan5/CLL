# Third-party frontend asset notices

The following pinned packages supply frontend code, CSS, icons, or fonts. Versions are kept in `package.json`/`package-lock.json`; run `npm run build:frontend` to generate or refresh the served assets. The build copies relevant upstream license files into `frontend/vendor/` where available.

| Package | Pinned version | License |
|---|---:|---|
| Tailwind CSS | 4.3.0 | MIT |
| `@tailwindcss/cli` | 4.3.0 | MIT |
| Chart.js | 4.5.1 | MIT |
| Font Awesome Free | 6.4.0 | Code: MIT; icons: CC BY 4.0; fonts: SIL OFL 1.1 |
| Fontsource Outfit Variable | 5.3.0 | SIL OFL 1.1 |
| Fontsource Plus Jakarta Sans Variable | 5.3.0 | SIL OFL 1.1 |
| `qrcode` | 1.5.4 | MIT |
| `@zxing/browser` | 0.1.5 | MIT |
| `@zxing/library` | 0.21.3 | MIT |

No user-generated case data is sent to a CDN for styling, charting, icon, font, or QR-generation assets.
