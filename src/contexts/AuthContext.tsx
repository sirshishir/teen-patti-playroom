
import React, { createContext, useContext, useState, useEffect } from 'react';

type User = {
  id: string;
  name: string;
  email: string;
  photoURL: string;
  balance: number;
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

  // Simulate loading user data from localStorage
  useEffect(() => {
    const storedUser = localStorage.getItem('teenpatti_user');
    if (storedUser) {
      setUser(JSON.parse(storedUser));
    }
    setLoading(false);
  }, []);

  // Mock login function - in a real app, you would connect to real auth providers
  const login = async (provider: 'google' | 'facebook') => {
    setLoading(true);
    try {
      // Simulate authentication delay
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      // Create mock user based on provider
      const mockUser: User = {
        id: `user_${Math.random().toString(36).substr(2, 9)}`,
        name: provider === 'google' ? 'Google User' : 'Facebook User',
        email: `user@${provider}.com`,
        photoURL: `https://ui-avatars.com/api/?name=${provider}+User&background=random`,
        balance: 1000
      };
      
      setUser(mockUser);
      localStorage.setItem('teenpatti_user', JSON.stringify(mockUser));
    } catch (error) {
      console.error("Login failed:", error);
    } finally {
      setLoading(false);
    }
  };

  const logout = async () => {
    setLoading(true);
    try {
      // Simulate logout delay
      await new Promise(resolve => setTimeout(resolve, 500));
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
