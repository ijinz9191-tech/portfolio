import { readFile, mkdir, copyFile, readdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { validatePublicData } from './public-contract.mjs';
const root = fileURLToPath(new URL('..', import.meta.url));
validatePublicData(JSON.parse(await readFile(resolve(root, 'public.data.json'), 'utf8')));
// Explicit allowlist: never copy the project tree or runtime state into public output.
const files = ['index.html', 'styles.css', 'app.js', 'public.data.json'];
await mkdir(resolve(root, 'dist'), { recursive: true });
const existing = await readdir(resolve(root, 'dist'));
if (existing.some(file => !files.includes(file))) throw new Error('Unexpected assets in dist; inspect them before publication. Build stopped.');
for (const file of files) await copyFile(resolve(root, file), resolve(root, 'dist', file));
console.log(`Built ${files.length} allowlisted public assets in dist/. External deployment not performed.`);
