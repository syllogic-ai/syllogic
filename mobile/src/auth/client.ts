import { createAuthClient } from 'better-auth/react';
import { expoClient } from '@better-auth/expo/client';
import * as SecureStore from 'expo-secure-store';

import { AUTH_URL } from '@/config';

// Talks to the same better-auth instance the web app (frontend/lib/auth.ts)
// exposes on the Next.js origin, so a Syllogic login works identically on
// web, iOS, and Mac. Data calls go to the separate FastAPI backend — see
// api/client.ts and config.ts.
export const authClient = createAuthClient({
  baseURL: AUTH_URL,
  plugins: [
    expoClient({
      scheme: 'syllogic',
      storagePrefix: 'syllogic',
      storage: SecureStore,
    }),
  ],
});
