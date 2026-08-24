import { FlatCompat } from "@eslint/eslintrc";
const compat = new FlatCompat({ baseDirectory: import.meta.dirname });
const config = [
  { ignores: [".next/**", ".next-dev/**", "coverage/**"] },
  ...compat.extends("next/core-web-vitals", "next/typescript"),
];

export default config;
