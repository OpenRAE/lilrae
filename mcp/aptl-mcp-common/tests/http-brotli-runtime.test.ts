import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import { createServer, type Server } from 'node:http';
import { once } from 'node:events';
import type { AddressInfo } from 'node:net';

import { HTTPClient } from '../src/http.js';

describe('HTTPClient malformed Brotli runtime handling', () => {
  let server: Server;
  let baseUrl: string;

  beforeAll(async () => {
    server = createServer((request, response) => {
      if (request.url === '/malformed') {
        response.writeHead(200, {
          'Content-Encoding': 'br',
          'Content-Type': 'application/json',
        });
        // Minimal invalid input, deliberately not a reproducer for the memory-
        // corruption flaw. The patched decoder must reject it safely.
        response.end(Buffer.from([0xff, 0xff, 0xff, 0xff]));
        return;
      }

      response.writeHead(200, { 'Content-Type': 'application/json' });
      response.end('{"alive":true}');
    });
    server.listen(0, '127.0.0.1');
    await once(server, 'listening');
    const address = server.address() as AddressInfo;
    baseUrl = `http://127.0.0.1:${address.port}`;
  });

  afterAll(async () => {
    server.close();
    await once(server, 'close');
  });

  it('rejects malformed Brotli through fetch and remains usable', async () => {
    const runtimeFetch = globalThis.fetch;
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation((input, init) => runtimeFetch(input, init));
    const client = new HTTPClient({
      baseUrl,
      auth: { type: 'apikey', header: 'X-Test-Key', apiKey: 'fixture' },
      verify_ssl: true,
      timeout: 2_000,
    });

    await expect(client.makeRequest('/malformed')).rejects.toThrow();

    const healthy = await client.makeRequest('/healthy');
    expect(healthy.data).toEqual({ alive: true });
    expect(fetchSpy).toHaveBeenCalledTimes(2);

    fetchSpy.mockRestore();
  });
});
