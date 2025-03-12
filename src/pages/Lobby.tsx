
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { useGame } from '@/contexts/GameContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { useToast } from '@/hooks/use-toast';

const Lobby = () => {
  const { user, logout } = useAuth();
  const { rooms, createRoom, joinRoom } = useGame();
  const navigate = useNavigate();
  const { toast } = useToast();
  
  const [newRoomName, setNewRoomName] = useState('');
  const [minBet, setMinBet] = useState(10);
  const [open, setOpen] = useState(false);

  const handleCreateRoom = () => {
    if (!newRoomName.trim()) {
      toast({
        title: "Required Field",
        description: "Please enter a room name",
        variant: "destructive",
      });
      return;
    }
    
    createRoom(newRoomName, minBet);
    setNewRoomName('');
    setMinBet(10);
    setOpen(false);
    
    toast({
      title: "Room Created",
      description: "Your new game room has been created!",
    });
  };

  const handleJoinRoom = (roomId: string) => {
    joinRoom(roomId);
    navigate('/game');
    
    toast({
      title: "Room Joined",
      description: "You've joined the game room!",
    });
  };

  const handleLogout = async () => {
    await logout();
    navigate('/');
    toast({
      title: "Logged Out",
      description: "You've been successfully logged out.",
    });
  };

  const handleProfile = () => {
    navigate('/profile');
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-indigo-900 to-purple-900">
      <div className="container mx-auto px-4 py-8">
        <div className="flex justify-between items-center mb-8">
          <h1 className="text-3xl font-bold text-white">Teen Patti Lobby</h1>
          
          <div className="flex items-center gap-4">
            {user && (
              <div className="flex items-center">
                <div className="text-white mr-4">
                  <span className="block font-medium">{user.name}</span>
                  <span className="block text-xs opacity-80">Balance: ₹{user.balance}</span>
                </div>
                <Button variant="outline" onClick={handleProfile}>Profile</Button>
                <Button variant="outline" className="ml-2" onClick={handleLogout}>Logout</Button>
              </div>
            )}
          </div>
        </div>
        
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl font-semibold text-white">Available Rooms</h2>
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button className="bg-green-600 hover:bg-green-700">Create Room</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Create a New Game Room</DialogTitle>
                <DialogDescription>
                  Set up your Teen Patti room and invite friends to play.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4 py-4">
                <div className="space-y-2">
                  <label htmlFor="roomName" className="text-sm font-medium">Room Name</label>
                  <Input
                    id="roomName"
                    value={newRoomName}
                    onChange={(e) => setNewRoomName(e.target.value)}
                    placeholder="Enter room name"
                  />
                </div>
                <div className="space-y-2">
                  <label htmlFor="minBet" className="text-sm font-medium">Minimum Bet (₹)</label>
                  <Input
                    id="minBet"
                    type="number"
                    min="10"
                    value={minBet}
                    onChange={(e) => setMinBet(Number(e.target.value))}
                  />
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
                <Button onClick={handleCreateRoom}>Create Room</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {rooms.map((room) => (
            <div key={room.id} className="bg-white rounded-lg shadow-lg overflow-hidden">
              <div className="p-6">
                <h3 className="text-xl font-bold mb-2">{room.name}</h3>
                <div className="text-sm text-gray-500 mb-4">
                  <p>Minimum Bet: ₹{room.minBet}</p>
                  <p>Status: {room.status === 'waiting' ? 'Waiting for players' : 'Game in progress'}</p>
                  <p>Players: {room.players.length}</p>
                </div>
                <Button 
                  className="w-full"
                  onClick={() => handleJoinRoom(room.id)}
                >
                  Join Room
                </Button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default Lobby;
