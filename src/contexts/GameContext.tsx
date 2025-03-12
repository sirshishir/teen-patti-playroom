
import React, { createContext, useContext, useState } from 'react';

// Types for game state
type Card = {
  suit: 'hearts' | 'diamonds' | 'clubs' | 'spades';
  value: number; // 1-13 (A, 2-10, J, Q, K)
};

type Player = {
  id: string;
  name: string;
  photoURL: string;
  cards: Card[];
  bet: number;
  isPlaying: boolean;
  isTurn: boolean;
};

type Room = {
  id: string;
  name: string;
  players: Player[];
  minBet: number;
  pot: number;
  status: 'waiting' | 'playing' | 'round_end';
  createdBy: string;
};

type GameContextType = {
  rooms: Room[];
  currentRoom: Room | null;
  playerCards: Card[];
  createRoom: (name: string, minBet: number) => void;
  joinRoom: (roomId: string) => void;
  leaveRoom: () => void;
  placeBet: (amount: number) => void;
  fold: () => void;
  showCards: () => void;
};

const GameContext = createContext<GameContextType | undefined>(undefined);

// Helper function to create a deck of cards
const createDeck = (): Card[] => {
  const suits: ('hearts' | 'diamonds' | 'clubs' | 'spades')[] = ['hearts', 'diamonds', 'clubs', 'spades'];
  const values = Array.from({ length: 13 }, (_, i) => i + 1);
  
  const deck: Card[] = [];
  
  for (const suit of suits) {
    for (const value of values) {
      deck.push({ suit, value });
    }
  }
  
  return shuffleDeck(deck);
};

// Shuffle the deck using Fisher-Yates algorithm
const shuffleDeck = (deck: Card[]): Card[] => {
  const shuffled = [...deck];
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  return shuffled;
};

export const GameProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [rooms, setRooms] = useState<Room[]>([
    {
      id: 'room1',
      name: 'Beginner Room',
      players: [],
      minBet: 10,
      pot: 0,
      status: 'waiting',
      createdBy: 'system',
    },
    {
      id: 'room2',
      name: 'Pro Players',
      players: [],
      minBet: 50,
      pot: 0,
      status: 'waiting',
      createdBy: 'system',
    },
  ]);
  const [currentRoom, setCurrentRoom] = useState<Room | null>(null);
  const [playerCards, setPlayerCards] = useState<Card[]>([]);

  // Create a new room
  const createRoom = (name: string, minBet: number) => {
    const newRoom: Room = {
      id: `room_${Math.random().toString(36).substr(2, 9)}`,
      name,
      players: [],
      minBet,
      pot: 0,
      status: 'waiting',
      createdBy: 'user', // In real app, use current user's ID
    };
    
    setRooms([...rooms, newRoom]);
  };

  // Join a room
  const joinRoom = (roomId: string) => {
    const room = rooms.find(r => r.id === roomId);
    if (!room) return;
    
    // In real app, create a player based on current user
    setCurrentRoom(room);
    
    // Deal cards to player (3 cards for Teen Patti)
    const deck = createDeck();
    setPlayerCards(deck.slice(0, 3));
  };

  // Leave the current room
  const leaveRoom = () => {
    setCurrentRoom(null);
    setPlayerCards([]);
  };

  // Place a bet
  const placeBet = (amount: number) => {
    if (!currentRoom) return;
    
    // Update room pot (in real app, update server state)
    const updatedRoom = { ...currentRoom, pot: currentRoom.pot + amount };
    setCurrentRoom(updatedRoom);
    
    // Update rooms list with the modified room
    setRooms(rooms.map(r => r.id === currentRoom.id ? updatedRoom : r));
  };

  // Fold cards
  const fold = () => {
    leaveRoom();
  };

  // Show cards (end of round)
  const showCards = () => {
    if (!currentRoom) return;
    
    // In real app, send cards to server to determine winner
    console.log("Player shows cards:", playerCards);
    
    // Reset for next round
    const deck = createDeck();
    setPlayerCards(deck.slice(0, 3));
  };

  return (
    <GameContext.Provider value={{
      rooms,
      currentRoom,
      playerCards,
      createRoom,
      joinRoom,
      leaveRoom,
      placeBet,
      fold,
      showCards
    }}>
      {children}
    </GameContext.Provider>
  );
};

export const useGame = () => {
  const context = useContext(GameContext);
  if (context === undefined) {
    throw new Error('useGame must be used within a GameProvider');
  }
  return context;
};
