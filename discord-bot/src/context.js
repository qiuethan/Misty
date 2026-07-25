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
import os from 'node:os';
import { createTranscribeClient } from './meeting/stt.js';
import * as audio from './meeting/audio.js';
import { createRecorder } from './meeting/recorder.js';
import { createMeetingReportService } from './meeting/reportService.js';
import { createSessionManager } from './meeting/sessionManager.js';

/**
 * Wire application services and deployment metadata once at startup.
 *
 * @param {object} config Validated bot configuration.
 * @returns {object} Shared application context passed through the router.
 */
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
  const reportService = createMeetingReportService({ llmClient });
  const transcribeClient = createTranscribeClient({ region: config.awsRegion });
  const sessionManager = createSessionManager({
    reportService,
    transcribeClient,
    audio,
    makeRecorder: ({ tmpDir }) => createRecorder({ tmpDir }),
    poster: async () => {}, // real poster injected by the adapter via setPoster()
    maxRecordingMs: config.maxRecordingMs,
    tmpRoot: os.tmpdir(),
  });
  return {
    directory,
    docClient,
    verification,
    linkService,
    emailService,
    seedService,
    teamService,
    docService,
    llmClient,
    helperService,
    sessionManager,
    discordGuildId: config.discordGuildId ?? null,
  };
}
