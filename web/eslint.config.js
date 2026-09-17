import js from '@eslint/js'
import jsxA11y from 'eslint-plugin-jsx-a11y'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import globals from 'globals'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  // Vendored registry sources (shadcn/ui, Bklit) are linted upstream, not here.
  {
    ignores: [
      'node_modules',
      'dist',
      'src/components/charts/**',
      'src/api/schema.d.ts',
      'src/components/ui/**',
      'src/components/shimmering-text.tsx',
      'playwright-report',
      'test-results',
      'coverage',
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.strict,
  jsxA11y.flatConfigs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: { ecmaVersion: 2023, globals: globals.browser },
    plugins: { 'react-hooks': reactHooks, 'react-refresh': reactRefresh },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      'no-console': 'error',
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/ban-ts-comment': 'error',
      '@typescript-eslint/consistent-type-imports': ['error', { fixStyle: 'inline-type-imports' }],
    },
  },
  {
    files: ['scripts/**', 'e2e/**', '*.config.{ts,js}'],
    languageOptions: { globals: globals.node },
  },
)
