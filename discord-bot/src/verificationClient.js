export class VerificationUnavailable extends Error {
  constructor(message) {
    super(message);
    this.name = 'VerificationUnavailable';
  }
}

export class RateLimited extends Error {
  constructor(message) {
    super(message);
    this.name = 'RateLimited';
  }
}

export class CodeExpired extends Error {
  constructor(message) {
    super(message);
    this.name = 'CodeExpired';
  }
}

export class TooManyAttempts extends Error {
  constructor(message) {
    super(message);
    this.name = 'TooManyAttempts';
  }
}

export class InvalidCode extends Error {
  constructor(message) {
    super(message);
    this.name = 'InvalidCode';
  }
}

export class NoPendingCode extends Error {
  constructor(message) {
    super(message);
    this.name = 'NoPendingCode';
  }
}

async function parseJson(resp) {
  try {
    return await resp.json();
  } catch {
    throw new VerificationUnavailable('malformed verification response');
  }
}

export function createVerificationClient({ baseUrl, apiKey, fetchImpl = fetch }) {
  const headers = { 'X-API-Key': apiKey, 'Content-Type': 'application/json' };

  async function send(path, options = {}) {
    try {
      return await fetchImpl(`${baseUrl}${path}`, { ...options, headers });
    } catch {
      throw new VerificationUnavailable('network error reaching verification service');
    }
  }

  return {
    async requestCode({ subject, email }) {
      const resp = await send('/verification/request-code', {
        method: 'POST',
        body: JSON.stringify({ subject, email }),
      });
      if (resp.status === 202) return;
      if (resp.status === 429) {
        const body = await resp.json().catch(() => ({}));
        throw new RateLimited(body.detail ?? 'rate_limited');
      }
      throw new VerificationUnavailable(`verification service returned ${resp.status}`);
    },

    async confirmCode({ subject, code }) {
      const resp = await send('/verification/confirm-code', {
        method: 'POST',
        body: JSON.stringify({ subject, code }),
      });
      if (resp.status === 200) return parseJson(resp);
      if (resp.status === 404) {
        const body = await resp.json().catch(() => ({}));
        throw new NoPendingCode(body.detail ?? 'no_pending_code');
      }
      if (resp.status === 410) {
        const body = await resp.json().catch(() => ({}));
        throw new CodeExpired(body.detail ?? 'expired');
      }
      if (resp.status === 429) {
        const body = await resp.json().catch(() => ({}));
        throw new TooManyAttempts(body.detail ?? 'too_many_attempts');
      }
      if (resp.status === 400) {
        const body = await resp.json().catch(() => ({}));
        throw new InvalidCode(body.detail ?? 'invalid_code');
      }
      throw new VerificationUnavailable(`verification service returned ${resp.status}`);
    },
  };
}
