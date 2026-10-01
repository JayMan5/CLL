import { cp, copyFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const frontend = path.join(repositoryRoot, "frontend");
const nodeModules = path.join(repositoryRoot, "node_modules");

async function copyFileToPackage(source, destination) {
  await mkdir(path.dirname(destination), { recursive: true });
  await copyFile(source, destination);
}

const chartRoot = path.join(nodeModules, "chart.js");
await copyFileToPackage(
  path.join(chartRoot, "LICENSE.md"),
  path.join(frontend, "vendor", "chartjs", "LICENSE.md"),
);

const fontAwesomeRoot = path.join(nodeModules, "@fortawesome", "fontawesome-free");
const fontAwesomeDestination = path.join(frontend, "vendor", "fontawesome");
await copyFileToPackage(
  path.join(fontAwesomeRoot, "css", "all.min.css"),
  path.join(fontAwesomeDestination, "css", "all.min.css"),
);
await cp(
  path.join(fontAwesomeRoot, "webfonts"),
  path.join(fontAwesomeDestination, "webfonts"),
  { recursive: true, force: true },
);
await copyFileToPackage(
  path.join(fontAwesomeRoot, "LICENSE.txt"),
  path.join(fontAwesomeDestination, "LICENSE.txt"),
);

const fontPackages = [
  {
    packageName: "outfit",
    family: "outfit",
    styles: ["outfit-latin-wght-normal.woff2", "outfit-latin-ext-wght-normal.woff2"],
  },
  {
    packageName: "plus-jakarta-sans",
    family: "plus-jakarta-sans",
    styles: ["plus-jakarta-sans-latin-wght-normal.woff2", "plus-jakarta-sans-latin-ext-wght-normal.woff2"],
  },
];

for (const font of fontPackages) {
  const sourceRoot = path.join(nodeModules, "@fontsource-variable", font.packageName);
  const destinationRoot = path.join(frontend, "vendor", "fonts", font.family);
  await copyFileToPackage(path.join(sourceRoot, "wght.css"), path.join(destinationRoot, "wght.css"));
  await copyFileToPackage(path.join(sourceRoot, "LICENSE"), path.join(destinationRoot, "LICENSE"));
  for (const fileName of font.styles) {
    await copyFileToPackage(
      path.join(sourceRoot, "files", fileName),
      path.join(destinationRoot, "files", fileName),
    );
  }
}

console.log("Copied pinned Font Awesome and Latin/Latin-ext variable font assets into frontend/vendor.");
