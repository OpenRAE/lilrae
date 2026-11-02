// Real SDK and common admission transport; the native effect is a local counter.
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { CallToolRequestSchema, ListToolsRequestSchema } from '@modelcontextprotocol/sdk/types.js';
import Ajv from 'ajv/dist/2020.js';
import { appendFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const [common, namesJson, configJson, effects] = process.argv.slice(2);
const { participantToolAdmission, participantToolRefusal } = await import(pathToFileURL(common));
const configuration = JSON.parse(configJson);
const admission = participantToolAdmission(configuration);
const names = JSON.parse(namesJson);
const inputSchema = {
  type: 'object', properties: {
    command: { type: 'string' }, endpoint: { type: 'string' }, method: { type: 'string' },
  }, additionalProperties: false,
};
const validate = new Ajv({ allErrors: true }).compile(inputSchema);
const server = new Server({ name: 'qualification', version: '1.0.0' }, { capabilities: { tools: {} } });
server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: names.map(name => ({ name, description: 'Admitted qualification action', inputSchema })),
}));
server.setRequestHandler(CallToolRequestSchema, async request => {
  const { name, arguments: args = {} } = request.params;
  if (!names.includes(name) || !validate(args) || !admission) return participantToolRefusal();
  return admission.execute(name, args, async () => {
    if (process.env.OPENROUTER_API_KEY) throw new Error('Model credential reached MCP child');
    appendFileSync(effects, JSON.stringify({ server: configuration.server, tool: name }) + '\n');
    return { content: [{ type: 'text', text: JSON.stringify({ success: true, observation: 'admitted' }) }] };
  }, async () => {});
});
await server.connect(new StdioServerTransport());
