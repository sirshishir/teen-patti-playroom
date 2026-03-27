import React, { createContext, useContext, useState, useRef, useEffect, useCallback } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type Suit = 'hearts' | 'diamonds' | 'clubs' | 'spades';
export type Card = { suit: Suit; value: number }; // 1=A, 2-10, 11=J, 12=Q, 13=K
export type HandRank = 'trail' | 'pure_sequence' | 'sequence' | 'color' | 'pair' | 'high_card';
export type HandEval = { rank: HandRank; score: number; label: string };
export type PlayerStatus = 'waiting' | 'blind' | 'seen' | 'folded' | 'all_in';
export type GamePhase = 'waiting' | 'dealing' | 'betting' | 'showdown' | 'round_over';
export type BotStyle = 'aggressive' | 'conservative' | 'balanced';

export type GamePlayer = {
  id: string;
  name: string;
  photoURL: string;
  balance: number;
  cards: Card[];
  currentBet: number;
  totalBet: number;
  status: PlayerStatus;
  isBot: boolean;
  isTurn: boolean;
  isDealer: boolean;
  seatIndex: number;
  botStyle?: BotStyle;
};

export type GameRoom = {
  id: string;
  code: string;
  name: string;
  players: GamePlayer[];
  minBet: number;
  pot: number;
  currentBet: number;
  bootAmount: number;
  phase: GamePhase;
  currentPlayerIndex: number;
  dealerIndex: number;
  roundNumber: number;
  winner: GamePlayer | null;
  winnerHand: HandEval | null;
  maxPlayers: number;
  fillWithBots: boolean;
  log: string[];
};

export type LobbyRoom = {
  id: string;
  code: string;
  name: string;
  playerCount: number;
  maxPlayers: number;
  minBet: number;
  status: 'waiting' | 'playing';
};

export type GameContextType = {
  lobbyRooms: LobbyRoom[];
  currentRoom: GameRoom | null;
  localPlayerId: string;

  // Lobby
  createRoom: (name: string, minBet: number, maxPlayers: number, fillWithBots: boolean) => void;
  joinRoom: (roomId: string) => void;
  joinRoomByCode: (code: string) => boolean;
  leaveRoom: () => void;

  // Game actions
  callBet: () => void;
  raiseBet: (amount: number) => void;
  foldHand: () => void;
  showCards: () => void;
  seeCards: () => void;
  playBlind: () => void;

  // Host
  startGame: () => void;
  addBot: (seatIndex: number) => void;

  // Derived helpers
  localPlayer: GamePlayer | null;
  isLocalPlayerTurn: boolean;
};

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const BOT_ROSTER: Array<{ name: string; photoURL: string; botStyle: BotStyle }> = [
  { name: 'Rahul K.', photoURL: 'https://ui-avatars.com/api/?name=Rahul+K&background=b91c1c&color=fff', botStyle: 'aggressive' },
  { name: 'Priya S.', photoURL: 'https://ui-avatars.com/api/?name=Priya+S&background=7c3aed&color=fff', botStyle: 'balanced' },
  { name: 'Amit V.',  photoURL: 'https://ui-avatars.com/api/?name=Amit+V&background=065f46&color=fff', botStyle: 'conservative' },
  { name: 'Nisha R.', photoURL: 'https://ui-avatars.com/api/?name=Nisha+R&background=b45309&color=fff', botStyle: 'aggressive' },
  { name: 'Dev M.',   photoURL: 'https://ui-avatars.com/api/?name=Dev+M&background=1d4ed8&color=fff', botStyle: 'balanced' },
];

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function generateRoomCode(): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
  let code = '';
  for (let i = 0; i < 6; i++) {
    code += chars[Math.floor(Math.random() * chars.length)];
  }
  return code;
}

function generateId(): string {
  return Math.random().toString(36).substr(2, 9);
}

function createDeck(): Card[] {
  const suits: Suit[] = ['hearts', 'diamonds', 'clubs', 'spades'];
  const deck: Card[] = [];
  for (const suit of suits) {
    for (let value = 1; value <= 13; value++) {
      deck.push({ suit, value });
    }
  }
  // Fisher-Yates shuffle
  for (let i = deck.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [deck[i], deck[j]] = [deck[j], deck[i]];
  }
  return deck;
}

function addLog(room: GameRoom, message: string): GameRoom {
  const log = [message, ...room.log].slice(0, 20);
  return { ...room, log };
}

// ---------------------------------------------------------------------------
// Hand Evaluation
// ---------------------------------------------------------------------------

export function evaluateHand(cards: Card[]): HandEval {
  if (cards.length !== 3) {
    return { rank: 'high_card', score: 0, label: 'Invalid Hand' };
  }

  const sorted = [...cards].sort((a, b) => b.value - a.value); // descending
  const values = sorted.map(c => c.value);
  const suits = sorted.map(c => c.suit);

  const isFlush = suits[0] === suits[1] && suits[1] === suits[2];
  const isTrail = values[0] === values[1] && values[1] === values[2];

  // Check for sequence (straight) - A can be high (A-K-Q) or low (A-2-3)
  function isSequential(vals: number[]): boolean {
    const s = [...vals].sort((a, b) => a - b);
    // Normal consecutive
    if (s[2] - s[1] === 1 && s[1] - s[0] === 1) return true;
    // Ace-low: A-2-3 → sorted as [1, 2, 3]
    if (s[0] === 1 && s[1] === 2 && s[2] === 3) return true;
    // Ace-high: A-K-Q → sorted as [1, 12, 13]
    if (s[0] === 1 && s[1] === 12 && s[2] === 13) return true;
    return false;
  }

  const isStraight = isSequential(values);

  // High card for sequence: treat A as 14 when high, 1 when low
  function sequenceHighCard(vals: number[]): number {
    const s = [...vals].sort((a, b) => a - b);
    // A-low (A-2-3): high card = 3
    if (s[0] === 1 && s[1] === 2 && s[2] === 3) return 3;
    // A-high (A-K-Q): high card = 14
    if (s[0] === 1 && s[1] === 12 && s[2] === 13) return 14;
    return s[2];
  }

  if (isTrail) {
    return {
      rank: 'trail',
      score: 600 + values[0],
      label: `Trail of ${cardValueLabel(values[0])}s`,
    };
  }

  if (isStraight && isFlush) {
    const high = sequenceHighCard(values);
    return {
      rank: 'pure_sequence',
      score: 500 + high,
      label: `Pure Sequence (${cardValueLabel(values[0])}-${cardValueLabel(values[1])}-${cardValueLabel(values[2])})`,
    };
  }

  if (isStraight) {
    const high = sequenceHighCard(values);
    return {
      rank: 'sequence',
      score: 400 + high,
      label: `Sequence (${cardValueLabel(values[0])}-${cardValueLabel(values[1])}-${cardValueLabel(values[2])})`,
    };
  }

  if (isFlush) {
    const [h, m, l] = values;
    const score = 300 + (h * 100 + m * 10 + l);
    return {
      rank: 'color',
      score,
      label: `Color (${cardValueLabel(h)}-${cardValueLabel(m)}-${cardValueLabel(l)})`,
    };
  }

  // Pair check
  let pairValue = -1;
  let kicker = -1;
  if (values[0] === values[1]) { pairValue = values[0]; kicker = values[2]; }
  else if (values[1] === values[2]) { pairValue = values[1]; kicker = values[0]; }
  else if (values[0] === values[2]) { pairValue = values[0]; kicker = values[1]; }

  if (pairValue !== -1) {
    return {
      rank: 'pair',
      score: 200 + pairValue * 10 + kicker,
      label: `Pair of ${cardValueLabel(pairValue)}s`,
    };
  }

  const [h, m, l] = values;
  return {
    rank: 'high_card',
    score: 100 + h * 100 + m * 10 + l,
    label: `High Card ${cardValueLabel(h)}`,
  };
}

function cardValueLabel(value: number): string {
  if (value === 1) return 'A';
  if (value === 11) return 'J';
  if (value === 12) return 'Q';
  if (value === 13) return 'K';
  return String(value);
}

// ---------------------------------------------------------------------------
// Bot AI
// ---------------------------------------------------------------------------

function botDecide(
  player: GamePlayer,
  room: GameRoom
): 'fold' | 'call' | 'raise' | 'show' {
  const hand = player.cards.length === 3 ? evaluateHand(player.cards) : null;
  const handScore = hand ? hand.score : 0;
  const style = player.botStyle ?? 'balanced';

  // Thresholds by rank score
  const isTrail = handScore >= 600;
  const isPureSeq = handScore >= 500 && handScore < 600;
  const isSeq = handScore >= 400 && handScore < 500;
  const isColor = handScore >= 300 && handScore < 400;
  const isPair = handScore >= 200 && handScore < 300;
  // high card otherwise

  // Amount needed to call
  const callAmount = player.status === 'seen'
    ? room.currentBet * 2 - player.currentBet
    : room.currentBet - player.currentBet;
  const safeBalance = player.balance - callAmount;

  // Never bust below 100
  if (safeBalance < 100 && callAmount > 0) {
    return 'fold';
  }

  // Random deviation ~20%
  const rand = Math.random();
  const deviate = rand < 0.20;

  let decision: 'fold' | 'call' | 'raise' | 'show' = 'call';

  if (style === 'aggressive') {
    if (isTrail || isPureSeq) decision = deviate ? 'call' : 'raise';
    else if (isSeq || isColor || isPair) decision = deviate ? 'fold' : 'raise';
    else decision = deviate ? 'fold' : 'call'; // high card: usually call
  } else if (style === 'conservative') {
    if (isTrail || isPureSeq) decision = deviate ? 'call' : 'raise';
    else if (isSeq) decision = deviate ? 'raise' : 'call';
    else if (isColor || isPair) decision = deviate ? 'fold' : 'call';
    else decision = deviate ? 'call' : 'fold'; // high card: usually fold
  } else {
    // balanced
    if (isTrail || isPureSeq || isSeq) decision = deviate ? 'call' : 'raise';
    else if (isColor) decision = deviate ? 'raise' : 'call';
    else if (isPair) decision = deviate ? 'fold' : 'call';
    else decision = deviate ? 'call' : 'fold';
  }

  // Only request show if there are exactly 2 active players and hand is strong
  const activePlayers = room.players.filter(p => p.status !== 'folded');
  if (activePlayers.length === 2 && (isTrail || isPureSeq || isSeq)) {
    if (Math.random() < 0.3) decision = 'show';
  }

  return decision;
}

// ---------------------------------------------------------------------------
// Game logic helpers
// ---------------------------------------------------------------------------

function makeBot(seatIndex: number, usedBotIndexes: number[], startingBalance: number): GamePlayer {
  const availableBots = BOT_ROSTER.filter((_, i) => !usedBotIndexes.includes(i));
  const botTemplate = availableBots.length > 0
    ? availableBots[Math.floor(Math.random() * availableBots.length)]
    : BOT_ROSTER[Math.floor(Math.random() * BOT_ROSTER.length)];

  return {
    id: `bot_${generateId()}`,
    name: botTemplate.name,
    photoURL: botTemplate.photoURL,
    balance: startingBalance,
    cards: [],
    currentBet: 0,
    totalBet: 0,
    status: 'waiting',
    isBot: true,
    isTurn: false,
    isDealer: false,
    seatIndex,
    botStyle: botTemplate.botStyle,
  };
}

function dealCards(room: GameRoom): GameRoom {
  const deck = createDeck();
  let cardIndex = 0;

  // Deal 3 cards round-robin starting from player after dealer
  const playerCount = room.players.length;
  const startIndex = (room.dealerIndex + 1) % playerCount;
  const order: number[] = [];
  for (let i = 0; i < playerCount; i++) {
    order.push((startIndex + i) % playerCount);
  }

  const players = room.players.map(p => ({ ...p, cards: [] as Card[], currentBet: 0 }));

  for (let card = 0; card < 3; card++) {
    for (const idx of order) {
      if (players[idx].status !== 'folded') {
        players[idx].cards.push(deck[cardIndex++]);
      }
    }
  }

  // Collect boot amount (ante)
  let pot = 0;
  for (let i = 0; i < players.length; i++) {
    const p = players[i];
    if (p.status !== 'folded') {
      const ante = Math.min(p.balance, room.bootAmount);
      players[i] = {
        ...p,
        balance: p.balance - ante,
        totalBet: ante,
        currentBet: 0,
        status: 'blind',
      };
      pot += ante;
    }
  }

  // Set first player's turn (player after dealer)
  const firstActive = order.find(i => players[i].status !== 'folded') ?? 0;
  players[firstActive] = { ...players[firstActive], isTurn: true };

  return {
    ...room,
    players,
    pot,
    currentBet: room.minBet,
    currentPlayerIndex: firstActive,
    phase: 'betting',
  };
}

function nextPlayerIndex(room: GameRoom, fromIndex: number): number {
  const count = room.players.length;
  for (let i = 1; i <= count; i++) {
    const idx = (fromIndex + i) % count;
    const p = room.players[idx];
    if (p.status !== 'folded' && p.status !== 'all_in') {
      return idx;
    }
  }
  return fromIndex; // fallback (shouldn't happen)
}

function activePlayers(room: GameRoom): GamePlayer[] {
  return room.players.filter(p => p.status !== 'folded');
}

function checkRoundEnd(room: GameRoom): boolean {
  const active = activePlayers(room);
  if (active.length <= 1) return true;

  // Check if all active players have bet the same amount (accounting for blind/seen multiplier)
  const allEqual = active.every(p => {
    const expected = p.status === 'seen' ? room.currentBet * 2 : room.currentBet;
    return p.currentBet >= expected;
  });

  if (allEqual && room.roundNumber >= 3) return true;

  return false;
}

function determineWinner(room: GameRoom): { winner: GamePlayer; hand: HandEval } {
  const active = activePlayers(room);
  let best: { player: GamePlayer; eval: HandEval } | null = null;

  for (const player of active) {
    if (player.cards.length === 3) {
      const eval_ = evaluateHand(player.cards);
      if (!best || eval_.score > best.eval.score) {
        best = { player, eval: eval_ };
      }
    }
  }

  if (!best) {
    // Fallback: last remaining player
    return { winner: active[0], hand: { rank: 'high_card', score: 0, label: 'Default Win' } };
  }

  return { winner: best.player, hand: best.eval };
}

function resolveWinner(room: GameRoom): GameRoom {
  const { winner, hand } = determineWinner(room);
  const players = room.players.map(p =>
    p.id === winner.id
      ? { ...p, balance: p.balance + room.pot }
      : p
  );
  let updated: GameRoom = {
    ...room,
    players,
    winner,
    winnerHand: hand,
    phase: 'round_over',
  };
  updated = addLog(updated, `${winner.name} wins the pot of ₹${room.pot} with ${hand.label}!`);
  return updated;
}

function prepareNextRound(room: GameRoom): GameRoom {
  const newDealerIndex = (room.dealerIndex + 1) % room.players.length;
  const players = room.players
    .filter(p => p.balance > 0) // remove broke players
    .map((p, i) => ({
      ...p,
      cards: [],
      currentBet: 0,
      totalBet: 0,
      status: 'waiting' as PlayerStatus,
      isTurn: false,
      isDealer: false,
      seatIndex: i,
    }));

  // Mark dealer
  const dealerIdx = newDealerIndex % players.length;
  if (players[dealerIdx]) {
    players[dealerIdx] = { ...players[dealerIdx], isDealer: true };
  }

  return {
    ...room,
    players,
    pot: 0,
    currentBet: room.minBet,
    phase: 'waiting',
    currentPlayerIndex: 0,
    dealerIndex: dealerIdx,
    roundNumber: 0,
    winner: null,
    winnerHand: null,
    log: room.log,
  };
}

// ---------------------------------------------------------------------------
// Lobby seed data
// ---------------------------------------------------------------------------

function makeLobbyRoom(id: string, code: string, name: string, playerCount: number, maxPlayers: number, minBet: number, status: 'waiting' | 'playing'): LobbyRoom {
  return { id, code, name, playerCount, maxPlayers, minBet, status };
}

const INITIAL_LOBBY_ROOMS: LobbyRoom[] = [
  makeLobbyRoom('lobby_seed1', 'FUN001', 'Desi Adda',     3, 6, 10,  'waiting'),
  makeLobbyRoom('lobby_seed2', 'PRO420', 'High Rollers',   5, 6, 100, 'playing'),
  makeLobbyRoom('lobby_seed3', 'MID555', 'Friends Table',  2, 4, 50,  'waiting'),
];

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const GameContext = createContext<GameContextType | undefined>(undefined);

const LOCAL_PLAYER_ID = Math.random().toString(36).substr(2, 9);

export const GameProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [lobbyRooms, setLobbyRooms] = useState<LobbyRoom[]>(INITIAL_LOBBY_ROOMS);
  const [currentRoom, setCurrentRoom] = useState<GameRoom | null>(null);

  // Map of all full game rooms keyed by id, for joinRoomByCode lookup
  const roomsMapRef = useRef<Map<string, GameRoom>>(new Map());

  // Bot timers
  const botTimersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  const localPlayerId = LOCAL_PLAYER_ID;

  // Clear all bot timers
  const clearBotTimers = useCallback(() => {
    botTimersRef.current.forEach(t => clearTimeout(t));
    botTimersRef.current = [];
  }, []);

  useEffect(() => {
    return () => clearBotTimers();
  }, [clearBotTimers]);

  // ---------------------------------------------------------------------------
  // Bot auto-play
  // ---------------------------------------------------------------------------

  const scheduleBotTurn = useCallback((room: GameRoom) => {
    const currentPlayer = room.players[room.currentPlayerIndex];
    if (!currentPlayer || !currentPlayer.isBot || room.phase !== 'betting') return;

    const delay = 1500 + Math.random() * 1000;
    const timer = setTimeout(() => {
      setCurrentRoom(prev => {
        if (!prev) return prev;
        const bot = prev.players[prev.currentPlayerIndex];
        if (!bot || !bot.isBot) return prev;

        // Bot may decide to see cards
        let updatedRoom = { ...prev };
        if (bot.status === 'blind' && Math.random() < 0.4) {
          const players = updatedRoom.players.map((p, i) =>
            i === updatedRoom.currentPlayerIndex ? { ...p, status: 'seen' as PlayerStatus } : p
          );
          updatedRoom = { ...updatedRoom, players };
        }

        const freshBot = updatedRoom.players[updatedRoom.currentPlayerIndex];
        const decision = botDecide(freshBot, updatedRoom);

        if (decision === 'fold') {
          updatedRoom = applyFold(updatedRoom, updatedRoom.currentPlayerIndex);
        } else if (decision === 'raise') {
          const raiseAmount = updatedRoom.minBet * 2;
          updatedRoom = applyRaise(updatedRoom, updatedRoom.currentPlayerIndex, raiseAmount);
        } else if (decision === 'show') {
          updatedRoom = applyShowdown(updatedRoom);
        } else {
          updatedRoom = applyCall(updatedRoom, updatedRoom.currentPlayerIndex);
        }

        roomsMapRef.current.set(updatedRoom.id, updatedRoom);
        return updatedRoom;
      });
    }, delay);

    botTimersRef.current.push(timer);
  }, []);

  // Watch currentRoom for bot turns
  useEffect(() => {
    if (!currentRoom) return;
    const currentPlayer = currentRoom.players[currentRoom.currentPlayerIndex];
    if (currentPlayer?.isBot && currentRoom.phase === 'betting') {
      scheduleBotTurn(currentRoom);
    }
  }, [currentRoom?.currentPlayerIndex, currentRoom?.phase, scheduleBotTurn]);

  // Auto-start next round after round_over
  useEffect(() => {
    if (currentRoom?.phase !== 'round_over') return;
    const timer = setTimeout(() => {
      setCurrentRoom(prev => {
        if (!prev || prev.phase !== 'round_over') return prev;
        const next = prepareNextRound(prev);
        roomsMapRef.current.set(next.id, next);
        return next;
      });
    }, 3000);
    botTimersRef.current.push(timer);
    return () => clearTimeout(timer);
  }, [currentRoom?.phase, currentRoom?.roundNumber]);

  // ---------------------------------------------------------------------------
  // Pure action helpers (operate on room state, return new room)
  // ---------------------------------------------------------------------------

  function advanceTurn(room: GameRoom): GameRoom {
    const active = activePlayers(room);
    if (active.length <= 1) {
      return resolveWinner(room);
    }

    // Check if betting round is complete
    const allBetsEqual = active.every(p => {
      const expected = p.status === 'seen' ? room.currentBet * 2 : room.currentBet;
      return p.currentBet >= expected;
    });

    const newRoundNumber = allBetsEqual ? room.roundNumber + 1 : room.roundNumber;

    if (allBetsEqual && newRoundNumber >= 3) {
      return resolveWinner({ ...room, roundNumber: newRoundNumber });
    }

    // Reset currentBet per player for next round if all equal
    let updatedRoom = { ...room, roundNumber: newRoundNumber };
    if (allBetsEqual) {
      const players = updatedRoom.players.map(p => ({ ...p, currentBet: 0 }));
      updatedRoom = { ...updatedRoom, players };
    }

    // Move to next player
    const oldIndex = updatedRoom.currentPlayerIndex;
    const players = updatedRoom.players.map(p => ({ ...p, isTurn: false }));
    updatedRoom = { ...updatedRoom, players };

    const nextIndex = nextPlayerIndex(updatedRoom, oldIndex);
    const updatedPlayers = updatedRoom.players.map((p, i) =>
      i === nextIndex ? { ...p, isTurn: true } : p
    );

    return { ...updatedRoom, players: updatedPlayers, currentPlayerIndex: nextIndex };
  }

  function applyFold(room: GameRoom, playerIndex: number): GameRoom {
    const players = room.players.map((p, i) =>
      i === playerIndex ? { ...p, status: 'folded' as PlayerStatus, isTurn: false } : p
    );
    let updated = addLog({ ...room, players }, `${room.players[playerIndex].name} folded.`);
    return advanceTurn(updated);
  }

  function applyCall(room: GameRoom, playerIndex: number): GameRoom {
    const player = room.players[playerIndex];
    const expectedBet = player.status === 'seen' ? room.currentBet * 2 : room.currentBet;
    const needed = Math.max(0, expectedBet - player.currentBet);
    const actual = Math.min(needed, player.balance);
    const newStatus: PlayerStatus = player.balance - actual <= 0 ? 'all_in' : player.status;

    const players = room.players.map((p, i) =>
      i === playerIndex
        ? { ...p, balance: p.balance - actual, currentBet: p.currentBet + actual, totalBet: p.totalBet + actual, status: newStatus, isTurn: false }
        : p
    );
    let updated = addLog({ ...room, players, pot: room.pot + actual }, `${player.name} called ₹${actual}.`);
    return advanceTurn(updated);
  }

  function applyRaise(room: GameRoom, playerIndex: number, amount: number): GameRoom {
    const player = room.players[playerIndex];
    const raiseAmount = Math.min(amount, player.balance);
    const newCurrentBet = player.status === 'seen'
      ? Math.max(room.currentBet, Math.floor(raiseAmount / 2))
      : Math.max(room.currentBet, raiseAmount);
    const newStatus: PlayerStatus = player.balance - raiseAmount <= 0 ? 'all_in' : player.status;

    const players = room.players.map((p, i) =>
      i === playerIndex
        ? { ...p, balance: p.balance - raiseAmount, currentBet: p.currentBet + raiseAmount, totalBet: p.totalBet + raiseAmount, status: newStatus, isTurn: false }
        : p
    );
    let updated = addLog(
      { ...room, players, pot: room.pot + raiseAmount, currentBet: newCurrentBet },
      `${player.name} raised by ₹${raiseAmount}.`
    );
    return advanceTurn(updated);
  }

  function applyShowdown(room: GameRoom): GameRoom {
    return resolveWinner({ ...room, phase: 'showdown' });
  }

  // ---------------------------------------------------------------------------
  // Lobby actions
  // ---------------------------------------------------------------------------

  const createRoom = useCallback((name: string, minBet: number, maxPlayers: number, fillWithBots: boolean) => {
    const roomId = `room_${generateId()}`;
    const code = generateRoomCode();

    const localPlayer: GamePlayer = {
      id: localPlayerId,
      name: 'You',
      photoURL: `https://ui-avatars.com/api/?name=You&background=f59e0b&color=fff`,
      balance: 1000,
      cards: [],
      currentBet: 0,
      totalBet: 0,
      status: 'waiting',
      isBot: false,
      isTurn: false,
      isDealer: false,
      seatIndex: 0,
    };

    const players: GamePlayer[] = [localPlayer];

    if (fillWithBots) {
      const botsToAdd = maxPlayers - 1;
      for (let i = 0; i < botsToAdd; i++) {
        const usedIndexes: number[] = [];
        players.push(makeBot(i + 1, usedIndexes, 1000));
      }
    }

    // Mark dealer (player after seat 0, or seat 0 if alone)
    const dealerIdx = players.length > 1 ? 1 : 0;
    players[dealerIdx] = { ...players[dealerIdx], isDealer: true };

    const newRoom: GameRoom = {
      id: roomId,
      code,
      name,
      players,
      minBet,
      pot: 0,
      currentBet: minBet,
      bootAmount: minBet,
      phase: 'waiting',
      currentPlayerIndex: 0,
      dealerIndex: dealerIdx,
      roundNumber: 0,
      winner: null,
      winnerHand: null,
      maxPlayers,
      fillWithBots,
      log: [`Room "${name}" created. Code: ${code}`],
    };

    roomsMapRef.current.set(roomId, newRoom);

    const lobbyEntry: LobbyRoom = {
      id: roomId,
      code,
      name,
      playerCount: players.length,
      maxPlayers,
      minBet,
      status: 'waiting',
    };

    setLobbyRooms(prev => [lobbyEntry, ...prev]);
    setCurrentRoom(newRoom);
  }, [localPlayerId]);

  const joinRoom = useCallback((roomId: string) => {
    const room = roomsMapRef.current.get(roomId);
    if (!room) return;
    if (room.players.length >= room.maxPlayers) return;

    const newPlayer: GamePlayer = {
      id: localPlayerId,
      name: 'You',
      photoURL: `https://ui-avatars.com/api/?name=You&background=f59e0b&color=fff`,
      balance: 1000,
      cards: [],
      currentBet: 0,
      totalBet: 0,
      status: 'waiting',
      isBot: false,
      isTurn: false,
      isDealer: false,
      seatIndex: room.players.length,
    };

    const updated: GameRoom = { ...room, players: [...room.players, newPlayer] };
    roomsMapRef.current.set(roomId, updated);
    setLobbyRooms(prev => prev.map(l => l.id === roomId ? { ...l, playerCount: updated.players.length } : l));
    setCurrentRoom(updated);
  }, [localPlayerId]);

  const joinRoomByCode = useCallback((code: string): boolean => {
    const upper = code.toUpperCase();
    for (const [id, room] of roomsMapRef.current.entries()) {
      if (room.code === upper) {
        joinRoom(id);
        return true;
      }
    }
    // Also check lobby seeded rooms (they don't have full GameRoom in map)
    return false;
  }, [joinRoom]);

  const leaveRoom = useCallback(() => {
    clearBotTimers();
    setCurrentRoom(null);
  }, [clearBotTimers]);

  const addBot = useCallback((seatIndex: number) => {
    setCurrentRoom(prev => {
      if (!prev) return prev;
      if (prev.players.length >= prev.maxPlayers) return prev;
      const usedIndexes: number[] = [];
      const bot = makeBot(seatIndex, usedIndexes, 1000);
      const updated = { ...prev, players: [...prev.players, bot] };
      roomsMapRef.current.set(updated.id, updated);
      return updated;
    });
  }, []);

  const startGame = useCallback(() => {
    setCurrentRoom(prev => {
      if (!prev) return prev;
      if (prev.players.length < 2) return prev;

      clearBotTimers();

      const dealing: GameRoom = addLog({ ...prev, phase: 'dealing' }, 'Dealing cards...');
      // Deal immediately in state but wait 1500ms before betting
      const dealt = dealCards(dealing);
      // Set phase to dealing first, then betting after delay
      const preDealt: GameRoom = { ...dealt, phase: 'dealing' };

      const timer = setTimeout(() => {
        setCurrentRoom(r => {
          if (!r || r.phase !== 'dealing') return r;
          const betting: GameRoom = addLog({ ...r, phase: 'betting' }, 'Betting begins!');
          roomsMapRef.current.set(betting.id, betting);
          return betting;
        });
      }, 1500);
      botTimersRef.current.push(timer);

      roomsMapRef.current.set(preDealt.id, preDealt);
      return preDealt;
    });
  }, [clearBotTimers]);

  // ---------------------------------------------------------------------------
  // Game actions
  // ---------------------------------------------------------------------------

  const callBet = useCallback(() => {
    setCurrentRoom(prev => {
      if (!prev || prev.phase !== 'betting') return prev;
      const localIdx = prev.players.findIndex(p => p.id === localPlayerId);
      if (localIdx === -1 || !prev.players[localIdx].isTurn) return prev;
      const updated = applyCall(prev, localIdx);
      roomsMapRef.current.set(updated.id, updated);
      return updated;
    });
  }, [localPlayerId]);

  const raiseBet = useCallback((amount: number) => {
    setCurrentRoom(prev => {
      if (!prev || prev.phase !== 'betting') return prev;
      const localIdx = prev.players.findIndex(p => p.id === localPlayerId);
      if (localIdx === -1 || !prev.players[localIdx].isTurn) return prev;
      const updated = applyRaise(prev, localIdx, amount);
      roomsMapRef.current.set(updated.id, updated);
      return updated;
    });
  }, [localPlayerId]);

  const foldHand = useCallback(() => {
    setCurrentRoom(prev => {
      if (!prev || prev.phase !== 'betting') return prev;
      const localIdx = prev.players.findIndex(p => p.id === localPlayerId);
      if (localIdx === -1 || !prev.players[localIdx].isTurn) return prev;
      const updated = applyFold(prev, localIdx);
      roomsMapRef.current.set(updated.id, updated);
      return updated;
    });
  }, [localPlayerId]);

  const showCards = useCallback(() => {
    setCurrentRoom(prev => {
      if (!prev || prev.phase !== 'betting') return prev;
      const localIdx = prev.players.findIndex(p => p.id === localPlayerId);
      if (localIdx === -1 || !prev.players[localIdx].isTurn) return prev;
      const updated = applyShowdown(prev);
      roomsMapRef.current.set(updated.id, updated);
      return updated;
    });
  }, [localPlayerId]);

  const seeCards = useCallback(() => {
    setCurrentRoom(prev => {
      if (!prev) return prev;
      const localIdx = prev.players.findIndex(p => p.id === localPlayerId);
      if (localIdx === -1) return prev;
      const player = prev.players[localIdx];
      if (player.status !== 'blind') return prev;
      const players = prev.players.map((p, i) =>
        i === localIdx ? { ...p, status: 'seen' as PlayerStatus } : p
      );
      const updated = addLog({ ...prev, players }, 'You looked at your cards.');
      roomsMapRef.current.set(updated.id, updated);
      return updated;
    });
  }, [localPlayerId]);

  const playBlind = useCallback(() => {
    // Player continues without seeing cards — just a no-op marker (status stays 'blind')
    // This is simply acknowledged; the UI can call callBet after
  }, []);

  // ---------------------------------------------------------------------------
  // Derived helpers
  // ---------------------------------------------------------------------------

  const localPlayer = currentRoom?.players.find(p => p.id === localPlayerId) ?? null;
  const isLocalPlayerTurn = localPlayer?.isTurn ?? false;

  // ---------------------------------------------------------------------------
  // Context value
  // ---------------------------------------------------------------------------

  const value: GameContextType = {
    lobbyRooms,
    currentRoom,
    localPlayerId,

    createRoom,
    joinRoom,
    joinRoomByCode,
    leaveRoom,

    callBet,
    raiseBet,
    foldHand,
    showCards,
    seeCards,
    playBlind,

    startGame,
    addBot,

    localPlayer,
    isLocalPlayerTurn,
  };

  return <GameContext.Provider value={value}>{children}</GameContext.Provider>;
};

export const useGame = (): GameContextType => {
  const context = useContext(GameContext);
  if (context === undefined) {
    throw new Error('useGame must be used within a GameProvider');
  }
  return context;
};
