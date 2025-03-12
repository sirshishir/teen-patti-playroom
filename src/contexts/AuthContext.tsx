
import React, { createContext, useContext, useState, useEffect } from 'react';

type User = {
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
  login: (provider: 'google' | 'facebook') => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // Load user data from localStorage
  useEffect(() => {
    const storedUser = localStorage.getItem('teenpatti_user');
    if (storedUser) {
      setUser(JSON.parse(storedUser));
    }
    setLoading(false);
  }, []);

  // Simulate Facebook SDK initialization
  useEffect(() => {
    // Add Facebook SDK script
    const facebookScript = document.createElement('script');
    facebookScript.async = true;
    facebookScript.defer = true;
    facebookScript.crossOrigin = 'anonymous';
    facebookScript.src = 'https://connect.facebook.net/en_US/sdk.js';
    
    // Initialize FB SDK when script loads
    facebookScript.onload = () => {
      window.FB.init({
        appId: '1234567890', // Replace with a real app ID in production
        cookie: true,
        xfbml: true,
        version: 'v16.0'
      });
    };
    
    document.head.appendChild(facebookScript);
    
    // Clean up
    return () => {
      if (document.head.contains(facebookScript)) {
        document.head.removeChild(facebookScript);
      }
    };
  }, []);

  const loginWithFacebook = (): Promise<User> => {
    return new Promise((resolve, reject) => {
      if (!window.FB) {
        console.error('Facebook SDK not loaded');
        reject(new Error('Facebook SDK not loaded'));
        return;
      }

      window.FB.login((response) => {
        if (response.authResponse) {
          window.FB.api('/me', { fields: 'name,email,picture' }, (userInfo) => {
            const facebookUser: User = {
              id: `fb_${userInfo.id}`,
              name: userInfo.name,
              email: userInfo.email || `user${userInfo.id}@facebook.com`,
              photoURL: userInfo.picture?.data?.url || `https://graph.facebook.com/${userInfo.id}/picture?type=large`,
              balance: 1000,
              provider: 'facebook'
            };
            resolve(facebookUser);
          });
        } else {
          reject(new Error('Facebook login failed or was cancelled'));
        }
      }, { scope: 'public_profile,email' });
    });
  };

  const loginWithGoogle = async (): Promise<User> => {
    // In a real app, implement Google OAuth here
    await new Promise(resolve => setTimeout(resolve, 1000));
    return {
      id: `google_${Math.random().toString(36).substr(2, 9)}`,
      name: 'Google User',
      email: 'user@google.com',
      photoURL: `https://ui-avatars.com/api/?name=Google+User&background=random`,
      balance: 1000,
      provider: 'google'
    };
  };

  const login = async (provider: 'google' | 'facebook') => {
    setLoading(true);
    try {
      let authUser: User;
      
      if (provider === 'facebook') {
        authUser = await loginWithFacebook();
      } else {
        authUser = await loginWithGoogle();
      }
      
      setUser(authUser);
      localStorage.setItem('teenpatti_user', JSON.stringify(authUser));
    } catch (error) {
      console.error("Login failed:", error);
      throw error;
    } finally {
      setLoading(false);
    }
  };

  const logout = async () => {
    setLoading(true);
    try {
      const currentUser = user;
      
      if (currentUser?.provider === 'facebook' && window.FB) {
        window.FB.logout(() => {
          console.log('Logged out from Facebook');
        });
      }
      
      // Clear local user data
      setUser(null);
      localStorage.removeItem('teenpatti_user');
    } catch (error) {
      console.error("Logout failed:", error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
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

// Add Facebook SDK type definition
declare global {
  interface Window {
    FB: {
      init: (options: {
        appId: string;
        cookie: boolean;
        xfbml: boolean;
        version: string;
      }) => void;
      login: (
        callback: (response: { authResponse: any }) => void,
        options: { scope: string }
      ) => void;
      api: (
        path: string,
        params: { fields: string },
        callback: (response: any) => void
      ) => void;
      logout: (callback: () => void) => void;
    };
  }
}
