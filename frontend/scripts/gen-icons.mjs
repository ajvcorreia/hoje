// Generates PNG icons from the SVG sources in public/icons. Run inside the frontend-tools container:
//   npm run gen:icons
import sharp from 'sharp';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const dir = new URL('../public/icons/', import.meta.url);
const any = await readFile(new URL('icon.svg', dir));
const maskable = await readFile(new URL('icon-maskable.svg', dir));

const jobs = [
  [any, 192, 'icon-192.png'],
  [any, 512, 'icon-512.png'],
  [maskable, 512, 'icon-512-maskable.png'],
  [maskable, 180, 'apple-touch-icon.png'],
];
for (const [svg, size, name] of jobs) {
  await sharp(svg, { density: 384 })
    .resize(size, size)
    .png()
    .toFile(fileURLToPath(new URL(name, dir)));
  console.log('wrote', name);
}
