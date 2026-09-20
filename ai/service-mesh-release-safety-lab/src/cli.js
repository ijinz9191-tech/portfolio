import { ReleaseController } from './controller.js';

if (process.argv[2] !== 'demo') {
  console.error('usage: node src/cli.js demo');
  process.exitCode = 2;
} else {
  const controller = new ReleaseController({ clusters: ['seoul-a', 'seoul-b'], approvalToken: 'approved' });
  controller.start({ releaseId: 'checkout-v42', service: 'checkout', version: '42.0.0', requester: 'platform-demo', approvalToken: 'approved' });
  const healthy = { errorRate: 0.002, p99LatencyMs: 180, saturation: 0.54 };
  for (let index = 0; index < 4; index += 1) controller.observe('checkout-v42', healthy);
  console.log(JSON.stringify({ release: controller.get('checkout-v42'), evidenceValid: controller.ledger.verify(), events: controller.ledger.list() }, null, 2));
}
