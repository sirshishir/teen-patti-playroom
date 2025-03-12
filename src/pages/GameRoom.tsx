
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useGame } from '@/contexts/GameContext';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { useToast } from '@/hooks/use-toast';
import { 
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

const GameRoom = () => {
  const { currentRoom, playerCards, leaveRoom, placeBet, fold, showCards } = useGame();
  const { user } = useAuth();
  const navigate = useNavigate();
  const { toast } = useToast();
  
  const [betAmount, setBetAmount] = useState(currentRoom?.minBet || 10);
  
  if (!currentRoom) {
    navigate('/lobby');
    return null;
  }
  
  const handleLeaveRoom = () => {
    leaveRoom();
    navigate('/lobby');
    toast({
      title: "Left Room",
      description: "You've left the game room.",
    });
  };
  
  const handlePlaceBet = () => {
    placeBet(betAmount);
    toast({
      title: "Bet Placed",
      description: `You've placed a bet of ₹${betAmount}.`,
    });
  };
  
  const handleFold = () => {
    fold();
    navigate('/lobby');
    toast({
      title: "Folded",
      description: "You've folded your cards and left the game.",
    });
  };
  
  const handleShowCards = () => {
    showCards();
    toast({
      title: "Cards Shown",
      description: "You've shown your cards!",
    });
  };
  
  // Helper to get card display name
  const getCardName = (value: number): string => {
    if (value === 1) return 'A';
    if (value === 11) return 'J';
    if (value === 12) return 'Q';
    if (value === 13) return 'K';
    return value.toString();
  };
  
  // Helper to get card color
  const getCardColor = (suit: string): string => {
    return suit === 'hearts' || suit === 'diamonds' ? 'text-red-600' : 'text-black';
  };
  
  // Helper to get suit symbol
  const getSuitSymbol = (suit: string): string => {
    switch (suit) {
      case 'hearts': return '♥';
      case 'diamonds': return '♦';
      case 'clubs': return '♣';
      case 'spades': return '♠';
      default: return '';
    }
  };

  return (
    <div className="min-h-screen bg-green-800 flex flex-col">
      {/* Game Header */}
      <div className="bg-green-900 p-4 text-white">
        <div className="container mx-auto flex justify-between items-center">
          <h1 className="text-xl font-bold">{currentRoom.name}</h1>
          <div className="flex items-center gap-4">
            <div>
              <span className="block text-sm">Pot: ₹{currentRoom.pot}</span>
              <span className="block text-xs">Min Bet: ₹{currentRoom.minBet}</span>
            </div>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="destructive" size="sm">Leave Game</Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Are you sure?</AlertDialogTitle>
                  <AlertDialogDescription>
                    If you leave now, you'll lose your current bet.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={handleLeaveRoom}>
                    Leave Game
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </div>
      </div>
      
      {/* Game Table */}
      <div className="flex-1 flex flex-col items-center justify-between p-4">
        {/* Opponent area (would be populated with actual players in a real implementation) */}
        <div className="w-full max-w-4xl grid grid-cols-3 gap-4 mb-8">
          {[1, 2, 3].map((_, index) => (
            <div key={index} className="flex flex-col items-center">
              <div className="w-16 h-16 rounded-full bg-gray-700 mb-2 flex items-center justify-center text-white">
                ?
              </div>
              <div className="text-white text-sm text-center">
                <p>Player {index + 1}</p>
                <p className="text-xs opacity-80">Waiting...</p>
              </div>
            </div>
          ))}
        </div>
        
        {/* Game actions and pot area */}
        <div className="bg-green-700 p-6 rounded-lg shadow-lg text-white text-center mb-8">
          <h2 className="text-2xl font-bold mb-2">Pot: ₹{currentRoom.pot}</h2>
          <div className="flex justify-center gap-4 mt-4">
            <Button 
              className="bg-blue-600 hover:bg-blue-700"
              onClick={handlePlaceBet}
            >
              Place Bet: ₹{betAmount}
            </Button>
            <Button 
              variant="secondary"
              onClick={() => setBetAmount(prev => Math.max(currentRoom.minBet, prev + 5))}
            >
              +5
            </Button>
            <Button 
              variant="secondary"
              onClick={() => setBetAmount(prev => Math.max(currentRoom.minBet, prev - 5))}
              disabled={betAmount <= currentRoom.minBet}
            >
              -5
            </Button>
            <Button 
              variant="destructive"
              onClick={handleFold}
            >
              Fold
            </Button>
            <Button 
              className="bg-amber-600 hover:bg-amber-700"
              onClick={handleShowCards}
            >
              Show Cards
            </Button>
          </div>
        </div>
        
        {/* Player's cards */}
        <div className="w-full max-w-4xl">
          <div className="mb-4 text-white text-center">
            <h3 className="font-bold">Your Cards</h3>
          </div>
          
          <div className="flex justify-center gap-4">
            {playerCards.map((card, index) => (
              <div 
                key={index} 
                className="w-28 h-40 bg-white rounded-lg shadow-lg flex flex-col items-center justify-between p-2 transform hover:scale-110 transition-transform border-2 border-gray-300"
                style={{ animationDelay: `${index * 100}ms` }}
              >
                <div className={`self-start text-lg font-bold ${getCardColor(card.suit)}`}>
                  {getCardName(card.value)}
                </div>
                <div className={`text-4xl ${getCardColor(card.suit)}`}>
                  {getSuitSymbol(card.suit)}
                </div>
                <div className={`self-end text-lg font-bold ${getCardColor(card.suit)} rotate-180`}>
                  {getCardName(card.value)}
                </div>
              </div>
            ))}
          </div>
          
          {/* Player info */}
          <div className="mt-6 text-center">
            <div className="inline-block bg-gray-800 text-white px-4 py-2 rounded-lg">
              <p className="font-bold">{user?.name}</p>
              <p className="text-sm">Balance: ₹{user?.balance}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default GameRoom;
