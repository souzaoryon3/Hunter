const { defineConfig } = require('eslint/config');
const expo = require('eslint-config-expo/flat');

module.exports = defineConfig([
  expo,
  // Compiler diagnostics remain advisory until this app opts into React Compiler.
  { rules: { 'react-hooks/refs': 'warn', 'react-hooks/set-state-in-effect': 'warn' } },
  { files: ['tools/*.cjs'], languageOptions: { globals: { __dirname: 'readonly', console: 'readonly' } } },
  { ignores: ['dist/**', 'android/**', 'ios/**', '.expo/**'] },
]);
