import { readFile, writeFile, rename, rm } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { randomUUID } from 'node:crypto';
import { validatePublicData } from './public-contract.mjs';
// The input must already be a deliberately exported public projection. This tool
// rejects unknown fields; it never derives a public projection from a private DB.
const input = process.argv[2];
if (!input) throw new Error('Usage: npm run update:public -- <sanitized-public-json-path>');
const data = validatePublicData(JSON.parse(await readFile(resolve(input), 'utf8')));
const destination = fileURLToPath(new URL('../public.data.json', import.meta.url));
const temporary = `${destination}.${randomUUID()}.tmp`;
try {
  await writeFile(temporary, `${JSON.stringify(data, null, 2)}\n`, { flag: 'wx' });
  await rename(temporary, destination);
} finally {
  await rm(temporary, { force: true });
}
console.log(`Updated public data revision ${data.revision}. Build and publication verification are separate gates.`);
