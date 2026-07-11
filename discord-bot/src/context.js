import { createDirectoryClient } from './directoryClient.js';
import { createDocClient } from './docClient.js';
import { createVerificationClient } from './verificationClient.js';
import { createLinkService } from './linkService.js';
import { createEmailService } from './emailService.js';
import { createSeedService } from './seedService.js';
import { createTeamService } from './teamService.js';
import { createDocService } from './docService.js';
import { createLlmClient } from './llmClient.js';
import { createHelperService } from './helperService.js';

// Wire the application services once. The router spreads this into every
// command's ctx (alongside the request-scoped principal).
export function createAppContext(config) {
  const directory = createDirectoryClient({
    baseUrl: config.directoryBaseUrl,
    apiKey: config.directoryApiKey,
  });
  const docClient = createDocClient({
    baseUrl: config.docBaseUrl,
    apiKey: config.docApiKey,
  });
  const verification = createVerificationClient({
    baseUrl: config.verificationBaseUrl,
    apiKey: config.verificationApiKey,
  });
  const linkService = createLinkService({ directory, verification });
  const emailService = createEmailService({ directory, verification });
  const seedService = createSeedService({ directory });
  const teamService = createTeamService({ directory });
  const docService = createDocService({ docClient, directory });
  const llmClient = createLlmClient({
    baseUrl: config.llmBaseUrl,
    apiKey: config.llmApiKey,
  });
  const helperService = createHelperService({ llmClient, directory });
  return { directory, docClient, verification, linkService, emailService, seedService, teamService, docService, llmClient, helperService };
}
