export class ControlPlaneError extends Error {
  constructor(code, message, details = {}) {
    super(message);
    this.name = 'ControlPlaneError';
    this.code = code;
    this.details = details;
  }
}
