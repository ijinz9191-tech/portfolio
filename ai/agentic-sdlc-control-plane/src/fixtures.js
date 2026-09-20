export const fleetFixture = () => [
  { id: 'rack-a-node-01', zone: 'az-a', state: 'READY', cards: [
    { id: 'npu-a1', memoryGiB: 64, health: 'HEALTHY', firmware: '2.4.1', features: ['fp16', 'collective'], leaseId: null },
    { id: 'npu-a2', memoryGiB: 64, health: 'HEALTHY', firmware: '2.4.1', features: ['fp16', 'collective'], leaseId: null }
  ] },
  { id: 'rack-b-node-01', zone: 'az-b', state: 'READY', cards: [
    { id: 'npu-b1', memoryGiB: 64, health: 'HEALTHY', firmware: '2.4.1', features: ['fp16', 'collective'], leaseId: null },
    { id: 'npu-b2', memoryGiB: 64, health: 'DEGRADED', firmware: '2.4.1', features: ['fp16'], leaseId: null }
  ] }
];

export const componentFixture = revision => ['driver', 'firmware', 'collective-library'].map(name => ({
  name,
  sourceRevision: revision,
  stages: ['build', 'unit', 'integration', 'hardware-simulation', 'security'].map(stage => ({ name: stage, status: 'PASSED' }))
}));
