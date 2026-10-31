// Cross-language fixture: real SDK/common/IPC; deterministic native substitutes.
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { fileURLToPath } from 'node:url';
import { createMCPServer } from '../../build/server.js';
import { SSHConnectionManager } from '../../build/ssh.js';
import { HTTPClient } from '../../build/http.js';

const configuration = JSON.parse(process.env.LILRAE_TEST_CONFIGURATION);
if (process.argv[2] === 'server') {
  let effects = 0;
  SSHConnectionManager.prototype.executeCommand = async () => ({
    code: 0, stdout: JSON.stringify({ effects: ++effects }), stderr: '',
  });
  HTTPClient.prototype.makeRequest = async () => ({ status: 200, data: { effects: ++effects } });
  await createMCPServer(configuration).start();
} else {
  const role = process.argv[2];
  const transport = new StdioClientTransport({
    command: process.execPath,
    args: [fileURLToPath(import.meta.url), 'server'],
    env: process.env,
    stderr: 'pipe',
  });
  const client = new Client({ name: 'lilrae-runtime-fixture', version: '1.0.0' });
  try {
    await client.connect(transport);
    const result = await client.callTool(role === 'red'
      ? { name: 'kali_run_command', arguments: { command: 'id' } }
      : { name: 'wazuh_api_call', arguments: { endpoint: '/agents', method: 'GET' } });
    console.log(JSON.stringify(result));
  } finally {
    await client.close();
  }
}
