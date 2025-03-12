
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { useToast } from '@/hooks/use-toast';

const Profile = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { toast } = useToast();
  
  if (!user) {
    navigate('/login');
    return null;
  }
  
  const handleLogout = async () => {
    await logout();
    navigate('/');
    toast({
      title: "Logged Out",
      description: "You've been successfully logged out.",
    });
  };
  
  const navigateToLobby = () => {
    navigate('/lobby');
  };

  const getProviderIcon = () => {
    if (user.provider === 'facebook') {
      return (
        <div className="bg-blue-600 text-white rounded-full p-1 w-6 h-6 flex items-center justify-center">
          <span className="text-lg font-bold">f</span>
        </div>
      );
    } else {
      return (
        <div className="bg-red-500 text-white rounded-full p-1 w-6 h-6 flex items-center justify-center">
          <span className="text-lg font-bold">G</span>
        </div>
      );
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-indigo-900 to-purple-900">
      <div className="container mx-auto px-4 py-8">
        <div className="max-w-2xl mx-auto bg-white rounded-lg shadow-xl overflow-hidden">
          <div className="bg-gradient-to-r from-purple-600 to-blue-600 px-6 py-12 text-white text-center">
            <div className="w-32 h-32 rounded-full border-4 border-white mx-auto mb-4 overflow-hidden shadow-xl">
              <img 
                src={user.photoURL} 
                alt={user.name} 
                className="w-full h-full object-cover"
              />
            </div>
            <h1 className="text-3xl font-bold">{user.name}</h1>
            <div className="flex items-center justify-center mt-2">
              <p className="text-blue-100 mr-2">{user.email}</p>
              {getProviderIcon()}
            </div>
          </div>
          
          <div className="p-6">
            <div className="bg-gray-100 rounded-lg p-4 mb-6">
              <h2 className="text-lg font-semibold mb-2">Account Information</h2>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-gray-500">User ID</p>
                  <p className="font-medium">{user.id}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Balance</p>
                  <p className="font-medium text-green-600">₹{user.balance}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Login Provider</p>
                  <p className="font-medium capitalize">{user.provider}</p>
                </div>
              </div>
            </div>
            
            <div className="space-y-4">
              <div className="bg-gray-100 rounded-lg p-4">
                <h2 className="text-lg font-semibold mb-2">Game Statistics</h2>
                <div className="grid grid-cols-3 gap-4 text-center">
                  <div>
                    <p className="text-sm text-gray-500">Games Played</p>
                    <p className="font-medium text-lg">0</p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-500">Wins</p>
                    <p className="font-medium text-lg">0</p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-500">Win Rate</p>
                    <p className="font-medium text-lg">0%</p>
                  </div>
                </div>
              </div>
            </div>
            
            <div className="mt-8 flex gap-4 justify-end">
              <Button variant="outline" onClick={navigateToLobby}>
                Return to Lobby
              </Button>
              <Button variant="destructive" onClick={handleLogout}>
                Logout
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Profile;
