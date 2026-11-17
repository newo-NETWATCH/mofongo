// Typed reader of the VITE_* variables. Components import `config`; nothing is hardcoded elsewhere.

function required(name: keyof ImportMetaEnv): string {
  const value = import.meta.env[name];
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`Missing ${String(name)}. Copy web/.env.example to web/.env.`);
  }
  return value.trim();
}

export interface AppConfig {
  apiBaseUrl: string;
  region: string;
  cognito: {
    userPoolId: string;
    clientId: string;
    authority: string;
    domain: string;
  };
  redirectUri: string;
  postLogoutUri: string;
}

export const config: AppConfig = {
  apiBaseUrl: required("VITE_API_BASE_URL").replace(/\/+$/, ""),
  region: required("VITE_AWS_REGION"),
  cognito: {
    userPoolId: required("VITE_COGNITO_USER_POOL_ID"),
    clientId: required("VITE_COGNITO_CLIENT_ID"),
    authority: required("VITE_COGNITO_AUTHORITY"),
    domain: required("VITE_COGNITO_DOMAIN").replace(/\/+$/, ""),
  },
  redirectUri: required("VITE_REDIRECT_URI"),
  postLogoutUri: required("VITE_POST_LOGOUT_URI"),
};
