import { MessageLedger } from './ledger.js';
import { createMessengerServer } from './http.js';

const port = Number(process.env.PORT ?? 3000);
const server = createMessengerServer(new MessageLedger());
server.listen(port, '127.0.0.1', () => console.log(`Messenger Reliability Lab listening on http://127.0.0.1:${port}`));
