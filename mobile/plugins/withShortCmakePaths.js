const { withAppBuildGradle } = require('expo/config-plugins');
const { createHash } = require('node:crypto');
const { homedir } = require('node:os');
const { join } = require('node:path');

// CMake hashes long object paths instead of exceeding Windows/Ninja MAX_PATH.
module.exports = config => withAppBuildGradle(config, config => {
  const marker = 'hunterShortCmakePaths';
  const id = createHash('sha256').update(config.modRequest.projectRoot).digest('hex').slice(0, 8);
  const staging = join(homedir(), '.hcx', id).replace(/\\/g, '/');
  if (config.modResults.language !== 'groovy') throw new Error('Hunter requires the Expo Groovy Android template.');
  if (!config.modResults.contents.includes(marker)) {
    const target = /defaultConfig\s*\{/;
    if (!target.test(config.modResults.contents)) throw new Error('Android defaultConfig was not found.');
    if (process.platform === 'win32') {
      config.modResults.contents = config.modResults.contents.replace(/android\s*\{/, match => `${match}
    externalNativeBuild { cmake { buildStagingDirectory file('${staging}') } }
`);
    }
    config.modResults.contents = config.modResults.contents.replace(target, match => `${match}
        // ${marker}
        externalNativeBuild {
            cmake { arguments "-DCMAKE_OBJECT_PATH_MAX=240" }
        }
`);
  }
  return config;
});
