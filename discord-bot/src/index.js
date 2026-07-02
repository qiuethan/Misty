import { Client, GatewayIntentBits } from 'discord.js';
import { loadConfig } from './config.js';
import { createAppContext } from './context.js';
import { commands } from './commands/index.js';
import { wireDiscordClient } from './adapters/discord.js';

async function main() {
  const config = loadConfig();
  const appContext = createAppContext(config);

  const enableDiscord = process.env.ENABLE_DISCORD !== 'false';
  const enableWeb = process.env.ENABLE_WEB === 'true';

  if (enableDiscord) {
    const client = new Client({ intents: [GatewayIntentBits.Guilds] });
    wireDiscordClient(client, { commands, appContext });
    client.once('ready', (c) => console.log(`Bot ready as ${c.user.tag}`));
    await client.login(config.discordToken).catch((err) => {
      console.error('Discord login failed:', err.message);
      process.exit(1);
    });
  }

  if (enableWeb) {
    // Task 6 wires the web server here.
    console.log('web mode: enabled (server wiring lands in Task 6)');
  }

  if (!enableDiscord && !enableWeb) {
    console.error('No surface enabled. Set ENABLE_DISCORD=true or ENABLE_WEB=true.');
    process.exit(2);
  }
}

main().catch((err) => {
  console.error('Fatal:', err);
  process.exit(1);
});
