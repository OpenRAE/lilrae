import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'fs';
import { tmpdir } from 'os';
import { join } from 'path';
import { pathToFileURL } from 'url';
import { describe, it, expect, vi } from 'vitest';
import { getTargetCredentials } from '../src/config.js';

describe('getTargetCredentials', () => {
  it('returns credentials for enabled container', () => {
    const config = {
      server: {
        configKey: 'test-container',
        targetName: 'Test Container'
      },
      containers: {
        'test-container': {
          ssh_key: '/path/to/key',
          ssh_user: 'testuser',
          ssh_port: 2022,
          container_ip: '172.20.0.50',
          enabled: true
        }
      }
    } as any;

    const creds = getTargetCredentials(config);

    expect(creds.sshKey).toBe('/path/to/key');
    expect(creds.username).toBe('testuser');
    expect(creds.port).toBe(2022);
    expect(creds.target).toBe('172.20.0.50');
  });

  it('coerces a string ssh_port (from ${APTL_HP_*} substitution) to a number', () => {
    const config = {
      server: { configKey: 'test-container', targetName: 'Test Container' },
      containers: {
        'test-container': {
          ssh_key: '/path/to/key',
          ssh_user: 'testuser',
          // After `${APTL_HP_KALI_SSH_PROXY_2023}` env substitution the port
          // arrives as a JSON string; the resolved SSH port must still be numeric.
          ssh_port: '2023',
          container_ip: '172.20.0.50',
          enabled: true
        }
      }
    } as any;

    const creds = getTargetCredentials(config);

    expect(creds.port).toBe(2023);
    expect(typeof creds.port).toBe('number');
  });

  it('throws error when container disabled', () => {
    const config = {
      server: {
        configKey: 'test-container',
        targetName: 'Test Container'
      },
      containers: {
        'test-container': {
          enabled: false
        }
      }
    } as any;

    expect(() => getTargetCredentials(config)).toThrow('Test Container instance is not enabled');
  });

  it('works with different container configs', () => {
    const config = {
      server: {
        configKey: 'kali',
        targetName: 'Kali Linux'
      },
      containers: {
        'kali': {
          ssh_key: '/kali/key',
          ssh_user: 'kali',
          ssh_port: 22,
          container_ip: '172.20.0.30',
          enabled: true
        }
      }
    } as any;

    const creds = getTargetCredentials(config);

    expect(creds.target).toBe('172.20.0.30');
    expect(creds.username).toBe('kali');
    expect(creds.sshKey).toBe('/kali/key');
    expect(creds.port).toBe(22);
  });

  it('uses correct configKey to find container', () => {
    const config = {
      server: {
        configKey: 'victim',
        targetName: 'Victim Container'
      },
      containers: {
        'victim': {
          ssh_key: '/victim/key',
          ssh_user: 'labadmin',
          ssh_port: 2022,
          container_ip: '172.20.0.20',
          enabled: true
        },
        'kali': {
          ssh_key: '/kali/key',
          ssh_user: 'kali',
          ssh_port: 22,
          container_ip: '172.20.0.30',
          enabled: true
        }
      }
    } as any;

    const creds = getTargetCredentials(config);

    expect(creds.target).toBe('172.20.0.20');
    expect(creds.username).toBe('labadmin');
  });
});

describe('startServer config path (#1344)', () => {
  it('loads docker-lab-config.json from a server directory whose path has a space and a non-ASCII character', async () => {
    const root = mkdtempSync(join(tmpdir(), 'aptl-start-server-'));
    const serverDir = join(root, 'lab checkout', 'mcp-café');
    mkdirSync(join(serverDir, 'build'), { recursive: true });
    writeFileSync(join(serverDir, 'docker-lab-config.json'), JSON.stringify({
      server: { name: 'test' }, lab: { name: 'spaced-lab' },
      api: { base_url: 'https://127.0.0.1:9200', ca_cert_path: 'certs/ca.pem' },
    }));
    // A server's import.meta.url percent-encodes the space and the "é".
    const callerMetaUrl = pathToFileURL(join(serverDir, 'build', 'index.js')).href;
    expect(callerMetaUrl).toContain('lab%20checkout/mcp-caf%C3%A9/build/index.js');
    const start = vi.fn(async () => undefined);
    const createMCPServer = vi.fn((_config: unknown) => ({ start }));
    vi.doMock('../src/server.js', () => ({ createMCPServer }));
    try {
      vi.stubEnv('APTL_MCP_DISABLE_DOTENV', '1');
      const { startServer } = await import('../src/index.js');
      await startServer(callerMetaUrl);
      const config = createMCPServer.mock.calls[0][0] as any;
      expect(config.lab.name).toBe('spaced-lab');
      // Paths that the loader resolves against the config file's directory use the decoded path too.
      expect(config.api.ca_cert_path).toBe(join(serverDir, 'certs', 'ca.pem'));
      expect(start).toHaveBeenCalledOnce();
    } finally {
      vi.doUnmock('../src/server.js');
      vi.unstubAllEnvs();
      rmSync(root, { recursive: true, force: true });
    }
  });
});
