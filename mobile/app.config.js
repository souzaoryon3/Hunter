module.exports = ({ config }) => {
  const preview = process.env.HUNTER_APK_PREVIEW === '1';
  const plugins = (config.plugins || []).filter(plugin =>
    (Array.isArray(plugin) ? plugin[0] : plugin) !== 'expo-build-properties');
  return {
    ...config,
    plugins: [...plugins, ['expo-build-properties', { android: { usesCleartextTraffic: preview } }], './plugins/withShortCmakePaths'],
  };
};
