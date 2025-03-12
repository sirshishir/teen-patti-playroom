
import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { useToast } from '@/hooks/use-toast';

const Login = () => {
  const { login, loading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { toast } = useToast();
  
  // Get the page they were trying to visit before being redirected to login
  const from = location.state?.from?.pathname || '/lobby';

  const handleLogin = async (provider: 'google' | 'facebook') => {
    try {
      await login(provider);
      toast({
        title: "Login successful!",
        description: `You've successfully logged in with ${provider}.`,
      });
      navigate(from, { replace: true });
    } catch (error) {
      toast({
        title: "Login failed",
        description: "There was a problem logging you in. Please try again.",
        variant: "destructive",
      });
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-b from-purple-900 to-indigo-900">
      <div className="bg-white p-8 rounded-lg shadow-lg max-w-md w-full">
        <h1 className="text-3xl font-bold text-center mb-6">Login to Teen Patti</h1>
        <p className="text-gray-600 text-center mb-8">
          Connect with your social account to start playing
        </p>
        
        <div className="space-y-4">
          <Button
            className="w-full py-2 bg-red-500 hover:bg-red-600 text-white font-medium rounded"
            onClick={() => handleLogin('google')}
            disabled={loading}
          >
            {loading ? 'Logging in...' : 'Login with Google'}
          </Button>
          
          <Button
            className="w-full py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded"
            onClick={() => handleLogin('facebook')}
            disabled={loading}
          >
            {loading ? 'Logging in...' : 'Login with Facebook'}
          </Button>
        </div>
        
        <div className="mt-6 text-center text-sm text-gray-500">
          <p>
            This is a demo application. No real authentication is performed.
          </p>
        </div>
      </div>
    </div>
  );
};

export default Login;
