// Kept as a compatible entry point; serves the app API and SQLite-backed UI.
import { createLabServer } from '../src/server.mjs';
import { LabStore } from '../src/store.mjs';
import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
const dir = fileURLToPath(new URL('../data/', import.meta.url));
await mkdir(dir, { recursive: true });
const port = Number(process.env.PORT || 4173);
if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Invalid PORT');
const store = new LabStore(dir + '/lab.sqlite');
const server = createLabServer({store});
server.listen(port, '127.0.0.1', () => console.log(`Incident Replay Lab: http://127.0.0.1:${port}`));
