// ESLint flat config.
// TypeScript 7 (the native compiler) has no JavaScript API, so typescript-eslint cannot parse with it.
// Babel's parser reads TS + JSX in pure JS instead; `tsc --noEmit` stays the source of truth for types
// and unused code, while ESLint covers React hooks, accessibility and code-quality rules.
import js from "@eslint/js";
import babelParser from "@babel/eslint-parser";
import jsxA11y from "eslint-plugin-jsx-a11y";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";

export default [
  { ignores: ["dist/", "node_modules/", "coverage/"] },
  js.configs.recommended,
  jsxA11y.flatConfigs.strict,
  {
    files: ["**/*.{ts,tsx,js}"],
    languageOptions: {
      parser: babelParser,
      parserOptions: {
        requireConfigFile: false,
        babelOptions: {
          babelrc: false,
          configFile: false,
          parserOpts: { plugins: ["typescript", "jsx"] },
        },
      },
      ecmaVersion: "latest",
      sourceType: "module",
      globals: { ...globals.browser, ...globals.serviceworker },
    },
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-hooks/exhaustive-deps": "error",
      // TypeScript already checks these (strict + noUnusedLocals/Parameters) and understands type-only names.
      "no-undef": "off",
      "no-unused-vars": "off",
      "no-restricted-syntax": ["error", { selector: "TSAnyKeyword", message: "Use a precise type or `unknown` instead of `any`." }],
      eqeqeq: ["error", "always", { null: "ignore" }],
      "no-console": ["error", { allow: ["warn", "error"] }],
      "prefer-const": "error",
      "no-var": "error",
      "object-shorthand": "error",
    },
  },
  {
    files: ["**/*.test.{ts,tsx}", "vite.config.ts", "eslint.config.js"],
    languageOptions: { globals: { ...globals.node } },
  },
];
