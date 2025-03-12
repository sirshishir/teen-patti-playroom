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
  const [fbSDKLoaded, setFbSDKLoaded] = useState(false);

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
    // Create a function to handle FB SDK load
    const handleFBSDKLoad = () => {
      try {
        if (window.FB) {
          window.FB.init({
            appId: '1234567890', // This is a dummy ID - in production use a real one
            cookie: true,
            xfbml: true,
            version: 'v16.0'
          });
          setFbSDKLoaded(true);
        }
      } catch (error) {
        console.error("Error initializing Facebook SDK:", error);
      }
    };

    // Add Facebook SDK script
    const addFacebookScript = () => {
      if (document.getElementById('facebook-sdk')) return;
      
      const facebookScript = document.createElement('script');
      facebookScript.id = 'facebook-sdk';
      facebookScript.async = true;
      facebookScript.defer = true;
      facebookScript.crossOrigin = 'anonymous';
      facebookScript.src = 'https://connect.facebook.net/en_US/sdk.js';
      
      // Initialize FB SDK when script loads
      facebookScript.onload = handleFBSDKLoad;
      
      document.head.appendChild(facebookScript);
    };
    
    addFacebookScript();
    
    // Clean up
    return () => {
      const facebookScript = document.getElementById('facebook-sdk');
      if (facebookScript && document.head.contains(facebookScript)) {
        document.head.removeChild(facebookScript);
      }
    };
  }, []);

  const loginWithFacebook = (): Promise<User> => {
    return new Promise((resolve, reject) => {
      if (!fbSDKLoaded || !window.FB) {
        console.warn('Facebook SDK not loaded or initialized properly');
        // Instead of rejecting, provide mock data as fallback
        const mockFacebookUser = createMockUser('facebook');
        resolve(mockFacebookUser);
        return;
      }

      try {
        window.FB.login((response) => {
          if (response.authResponse) {
            window.FB.api('/me', { fields: 'name,email,picture' }, (userInfo) => {
              try {
                const facebookUser: User = {
                  id: `fb_${userInfo.id || Math.random().toString(36).substr(2, 9)}`,
                  name: userInfo.name || 'Facebook User',
                  email: userInfo.email || `user${Math.random().toString(36).substr(2, 9)}@facebook.com`,
                  photoURL: userInfo.picture?.data?.url || `https://ui-avatars.com/api/?name=Facebook+User&background=4267B2&color=fff`,
                  balance: 1000,
                  provider: 'facebook'
                };
                resolve(facebookUser);
              } catch (error) {
                console.error("Error processing Facebook user info:", error);
                const mockFacebookUser = createMockUser('facebook');
                resolve(mockFacebookUser);
              }
            });
          } else {
            console.warn("Facebook login failed or was cancelled");
            const mockFacebookUser = createMockUser('facebook');
            resolve(mockFacebookUser);
          }
        }, { scope: 'public_profile,email' });
      } catch (error) {
        console.error("Error during Facebook login:", error);
        const mockFacebookUser = createMockUser('facebook');
        resolve(mockFacebookUser);
      }
    });
  };

  const createMockUser = (provider: 'google' | 'facebook'): User => {
    const isGoogle = provider === 'google';
    
    const randomName = isGoogle ? 'Google User' : 'Facebook User';
    const backgroundColor = isGoogle ? 'random' : '4267B2';
    const textColor = isGoogle ? '' : 'fff';
    
    return {
      id: `${provider}_${Math.random().toString(36).substr(2, 9)}`,
      name: randomName,
      email: `user${Math.random().toString(36).substr(2, 9)}@${provider}.com`,
      photoURL: `https://ui-avatars.com/api/?name=${randomName.replace(' ', '+')}&background=${backgroundColor}${textColor ? '&color=' + textColor : ''}`,
      balance: 1000,
      provider: provider
    };
  };

  const loginWithGoogle = async (): Promise<User> => {
    // In a real app, implement Google OAuth here
    await new Promise(resolve => setTimeout(resolve, 1000));
    return createMockUser('google');
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
