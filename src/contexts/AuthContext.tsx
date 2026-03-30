import React, { createContext, useContext, useState, useEffect } from 'react';
import {
  GoogleAuthProvider,
  FacebookAuthProvider,
  signInWithPopup,
  signOut,
  onAuthStateChanged,
  User as FirebaseUser,
} from 'firebase/auth';
import { auth, isFirebaseConfigured } from '@/lib/firebase';

// ─── Types ───────────────────────────────────────────────────────────────────

export type User = {
  id: string;
  name: string;
  email: string;
  photoURL: string;
  balance: number;
  provider: 'google' | 'facebook';
};

type AuthContextType = {
  user: User | null;
  loading: boolean;
  configured: boolean;
  login: (provider: 'google' | 'facebook') => Promise<void>;
  loginAsGuest: () => void; // DEV BYPASS — remove button in Login.tsx to disable
  logout: () => Promise<void>;
};

// ─── Context ─────────────────────────────────────────────────────────────────

const AuthContext = createContext<AuthContextType | undefined>(undefined);

function mapFirebaseUser(fbUser: FirebaseUser, provider: 'google' | 'facebook'): User {
  const saved = localStorage.getItem(`balance_${fbUser.uid}`);
  return {
    id: fbUser.uid,
    name: fbUser.displayName || (provider === 'google' ? 'Google User' : 'Facebook User'),
    email: fbUser.email || '',
    photoURL:
      fbUser.photoURL ||
      `https://ui-avatars.com/api/?name=${encodeURIComponent(fbUser.displayName || 'Player')}&background=d4af37&color=000`,
    balance: saved ? parseInt(saved, 10) : 5000,
    provider,
  };
}

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // Listen to Firebase auth state (survives page refresh automatically)
  useEffect(() => {
    if (!isFirebaseConfigured || !auth) {
      setLoading(false);
      return;
    }

    const unsubscribe = onAuthStateChanged(auth, (fbUser) => {
      if (fbUser) {
        const providerStr = fbUser.providerData[0]?.providerId ?? '';
        const provider: 'google' | 'facebook' = providerStr.includes('facebook')
          ? 'facebook'
          : 'google';
        setUser(mapFirebaseUser(fbUser, provider));
      } else {
        setUser(null);
      }
      setLoading(false);
    });

    return unsubscribe;
  }, []);

  const login = async (provider: 'google' | 'facebook') => {
    if (!isFirebaseConfigured || !auth) {
      throw new Error('Firebase is not configured. See AUTH_SETUP.md for setup instructions.');
    }

    setLoading(true);
    try {
      const authProvider =
        provider === 'google'
          ? new GoogleAuthProvider()
          : new FacebookAuthProvider();

      if (provider === 'facebook') {
        (authProvider as FacebookAuthProvider).addScope('public_profile');
        (authProvider as FacebookAuthProvider).addScope('email');
      }

      const result = await signInWithPopup(auth, authProvider);
      const mappedUser = mapFirebaseUser(result.user, provider);
      setUser(mappedUser);
    } finally {
      setLoading(false);
    }
  };

  // DEV BYPASS — creates a local guest session without Firebase
  // To disable: remove the "Skip Login" button from src/pages/Login.tsx
  const loginAsGuest = () => {
    const guest: User = {
      id: `guest_${Math.random().toString(36).substr(2, 8)}`,
      name: 'Guest Player',
      email: 'guest@demo.local',
      photoURL: 'https://ui-avatars.com/api/?name=Guest+Player&background=d4af37&color=000',
      balance: 5000,
      provider: 'google',
    };
    setUser(guest);
  };

  const logout = async () => {
    if (!auth) return;
    setLoading(true);
    try {
      await signOut(auth);
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthContext.Provider value={{ user, loading, configured: isFirebaseConfigured, login, loginAsGuest, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
