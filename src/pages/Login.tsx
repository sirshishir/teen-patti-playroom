
import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { useToast } from '@/hooks/use-toast';
import { Facebook, Mail } from 'lucide-react';

const Login = () => {
  const { login, loading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { toast } = useToast();
  const [loadingProvider, setLoadingProvider] = useState<'google' | 'facebook' | null>(null);
  
  // Get the page they were trying to visit before being redirected to login
  const from = location.state?.from?.pathname || '/lobby';

  const handleLogin = async (provider: 'google' | 'facebook') => {
    setLoadingProvider(provider);
    try {
      await login(provider);
      toast({
        title: "Login successful!",
        description: `You've successfully logged in with ${provider === 'google' ? 'Google' : 'Facebook'}.`,
      });
      navigate(from, { replace: true });
    } catch (error) {
      toast({
        title: "Login failed",
        description: "There was a problem logging you in. Please try again.",
        variant: "destructive",
      });
    } finally {
      setLoadingProvider(null);
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
            className="w-full flex items-center justify-center gap-2 py-2 bg-red-500 hover:bg-red-600 text-white font-medium rounded"
            onClick={() => handleLogin('google')}
            disabled={loading || loadingProvider !== null}
          >
            {loadingProvider === 'google' ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent"></div>
                <span>Logging in...</span>
              </>
            ) : (
              <>
                <Mail size={18} />
                <span>Login with Google</span>
              </>
            )}
          </Button>
          
          <Button
            className="w-full flex items-center justify-center gap-2 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded"
            onClick={() => handleLogin('facebook')}
            disabled={loading || loadingProvider !== null}
          >
            {loadingProvider === 'facebook' ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent"></div>
                <span>Logging in...</span>
              </>
            ) : (
              <>
                <Facebook size={18} />
                <span>Login with Facebook</span>
              </>
            )}
          </Button>
        </div>
        
        <div className="mt-6 text-center text-sm text-gray-500">
          <p>
            This is a demo application. No real authentication is performed.
          </p>
          <p className="mt-2">
            Demo mode: You'll be provided with a simulated user account.
          </p>
        </div>
      </div>
    </div>
  );
};

export default Login;
