
import React from 'react';
import { Button } from "@/components/ui/button";
import { useNavigate } from 'react-router-dom';
import { useToast } from "@/hooks/use-toast";

const Index = () => {
  const navigate = useNavigate();
  const { toast } = useToast();

  const handlePlay = () => {
    navigate('/login');
    toast({
      title: "Welcome!",
      description: "Please login to continue playing Teen Patti.",
    });
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-b from-purple-900 to-indigo-900">
      <div className="max-w-4xl w-full px-4 py-8 text-center">
        <h1 className="text-5xl font-bold mb-6 text-white">Teen Patti Online</h1>
        <p className="text-xl text-gray-200 mb-8">
          Join friends and play the popular Indian card game online
        </p>
        <div className="space-y-4">
          <Button 
            size="lg" 
            className="bg-gradient-to-r from-red-500 to-amber-500 hover:from-red-600 hover:to-amber-600 text-white font-bold py-3 px-8 rounded-lg shadow-lg transition-all"
            onClick={handlePlay}
          >
            Play Now
          </Button>
        </div>
        <div className="mt-12 text-gray-300 text-sm">
          <p>Login with your social accounts and join game rooms to play with friends</p>
        </div>
      </div>
    </div>
  );
};

export default Index;
