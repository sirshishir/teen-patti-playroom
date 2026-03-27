# Firebase Authentication Setup — Teen Patti Playroom

React 18 + TypeScript + Vite + Firebase Auth. Covers real Google and Facebook login end-to-end.

---

## 1. Firebase Project Setup

1. Go to [console.firebase.google.com](https://console.firebase.google.com)
2. Create a new project or open an existing one
3. Navigate to **Project Settings → General → Your apps → Add app → Web** (`</>`)
4. Register the app (name it "Teen Patti Playroom"), skip Firebase Hosting
5. Copy the `firebaseConfig` object — you'll need all six values:

```js
const firebaseConfig = {
  apiKey: "...",
  authDomain: "...",
  projectId: "...",
  storageBucket: "...",
  messagingSenderId: "...",
  appId: "..."
};
```

---

## 2. Environment Variables

Create `.env.local` in the project root (same level as `package.json`):

```env
VITE_FIREBASE_API_KEY=...
VITE_FIREBASE_AUTH_DOMAIN=...
VITE_FIREBASE_PROJECT_ID=...
VITE_FIREBASE_STORAGE_BUCKET=...
VITE_FIREBASE_MESSAGING_SENDER_ID=...
VITE_FIREBASE_APP_ID=...
```

> **Important:** `.env.local` is gitignored by default — never commit it. All variables must be prefixed with `VITE_` or Vite will not expose them to the browser.

---

## 3. Install Firebase

```bash
bun add firebase
```

---

## 4. Enable Google Sign-In (Firebase Console)

1. **Firebase Console → Authentication → Sign-in method**
2. Click **Google** → toggle **Enable**
3. Set a **support email** (required)
4. Click **Save**

That's it — no external portal needed for Google.

---

## 5. Enable Facebook Sign-In (Firebase Console + Meta Developer Portal)

### 5a. Meta Developer Portal Setup

1. Go to [developers.facebook.com](https://developers.facebook.com) → **My Apps → Create App**
2. Select type **Consumer**
3. App name: `Teen Patti Playroom`, add your email → **Create app**
4. From the app **Dashboard → Add Product → Facebook Login → Web**
5. Enter your site URL (e.g. `https://falash-patti.netlify.app`), click **Save**
6. Navigate to **Facebook Login → Settings** (left sidebar)
7. Under **Valid OAuth Redirect URIs**, add:
   ```
   https://<YOUR-AUTH-DOMAIN>.firebaseapp.com/__/auth/handler
   ```
   Replace `<YOUR-AUTH-DOMAIN>` with the `authDomain` value from your `firebaseConfig` (e.g. `your-project-id`).
8. Click **Save Changes**
9. Go to **App Dashboard → Settings → Basic** → copy your **App ID** and **App Secret**

### 5b. Firebase Console Setup

1. **Firebase Console → Authentication → Sign-in method → Facebook** → toggle **Enable**
2. Paste your **App ID** and **App Secret** from Meta
3. Copy the **OAuth redirect URI** shown in Firebase — it looks like:
   ```
   https://your-project-id.firebaseapp.com/__/auth/handler
   ```
4. Paste that URI into **Meta Developer Portal → Facebook Login → Settings → Valid OAuth Redirect URIs** (if not already added in 5a)
5. Click **Save** in both Firebase and Meta

### 5c. Facebook App Review

- **Testing your own accounts only:** No review needed. Add testers under **App Dashboard → Roles → Test Users**.
- **Public users:** Submit **Facebook Login** for app review. You'll need `public_profile` and `email` permissions approved before the app goes live.

---

## 6. Netlify Domain (Important for OAuth Redirect)

When deploying to `falash-patti.netlify.app`:

1. **Firebase Console → Authentication → Settings → Authorized domains → Add domain**
   ```
   falash-patti.netlify.app
   ```
2. Click **Add**

> The Meta Developer Portal does **not** need a separate Netlify URL in its redirect URIs. Firebase's handler URL (`firebaseapp.com/__/auth/handler`) acts as the intermediary and redirects back to your Netlify app — so only the Firebase URL needs to be in Meta's allowed list.

---

## 7. How the Firebase Auth Code Works in This App

| File | Role |
|------|------|
| `src/lib/firebase.ts` | Initializes the Firebase app using `VITE_FIREBASE_*` env vars and exports the `auth` instance |
| `src/contexts/AuthContext.tsx` | Provides `signInWithGoogle` and `signInWithFacebook` via `signInWithPopup(auth, provider)` |

Key behaviors:

- **`signInWithPopup`** opens the provider's login window. On success, Firebase returns a `UserCredential` containing `user.displayName`, `user.email`, and `user.photoURL` — populated automatically from the provider.
- **Auth state persistence** is handled by Firebase automatically. The user stays logged in across page refreshes without any extra code.
- If the `VITE_FIREBASE_*` variables are missing or empty, `src/lib/firebase.ts` will not initialize correctly and the app will display a **"Login not configured"** error. Always verify the `.env.local` file exists and is complete.

---

## 8. Testing Checklist

- [ ] `.env.local` created with all 6 `VITE_FIREBASE_*` variables filled in
- [ ] Firebase Google sign-in enabled (Authentication → Sign-in method)
- [ ] Firebase Facebook sign-in enabled with correct App ID and App Secret
- [ ] Meta Developer Portal → Facebook Login → Settings → Valid OAuth Redirect URIs contains `https://<authDomain>.firebaseapp.com/__/auth/handler`
- [ ] Firebase Authorized domains includes `falash-patti.netlify.app`
- [ ] `bun add firebase` has been run
- [ ] `bun run build` completes without errors
- [ ] Facebook login opens a real popup (not an auto-login or error screen)
- [ ] Google login opens the real Google account chooser popup

---

## 9. Common Errors and Fixes

| Error | Fix |
|-------|-----|
| `auth/configuration-not-found` | Check `.env.local` exists, all 6 vars are set, and all start with `VITE_`. Restart the dev server after editing env files. |
| `auth/unauthorized-domain` | Add your domain to **Firebase Console → Authentication → Settings → Authorized domains** |
| `Can't load URL: The domain of this URL isn't included in the app's domains` | Add the Firebase redirect URI (`https://<authDomain>.firebaseapp.com/__/auth/handler`) to **Meta Developer Portal → Facebook Login → Settings → Valid OAuth Redirect URIs** |
| `auth/operation-not-allowed` | The sign-in provider is not enabled — go to **Firebase Console → Authentication → Sign-in method** and enable it |
| Facebook login works in dev but not in production | The Netlify domain is missing from **Firebase Console → Authentication → Settings → Authorized domains** |
