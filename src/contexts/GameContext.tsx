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

export type SideShowRequest = {
  requesterId: string;
  targetId: string;
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
  previousPlayerIndex: number;
  dealerIndex: number;
  roundNumber: number;
  winner: GamePlayer | null;
  winnerHand: HandEval | null;
  maxPlayers: number;
  fillWithBots: boolean;
  log: string[];
  sideShowRequest: SideShowRequest | null;
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

  createRoom: (name: string, minBet: number, maxPlayers: number, fillWithBots: boolean) => void;
  joinRoom: (roomId: string) => void;
  joinRoomByCode: (code: string) => boolean;
  leaveRoom: () => void;

  callBet: () => void;
  raiseBet: (amount: number) => void;
  foldHand: () => void;
  showCards: () => void;
  seeCards: () => void;
  playBlind: () => void;
  requestSideShow: () => void;
  respondSideShow: (accept: boolean) => void;

  startGame: () => void;
  addBot: (seatIndex: number) => void;

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
  for (let i = 0; i < 6; i++) code += chars[Math.floor(Math.random() * chars.length)];
  return code;
}

function generateId(): string {
  return Math.random().toString(36).substr(2, 9);
}

function createDeck(): Card[] {
  const suits: Suit[] = ['hearts', 'diamonds', 'clubs', 'spades'];
  const deck: Card[] = [];
  for (const suit of suits) {
    for (let value = 1; value <= 13; value++) deck.push({ suit, value });
  }
  for (let i = deck.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [deck[i], deck[j]] = [deck[j], deck[i]];
  }
  return deck;
}

function addLog(room: GameRoom, message: string): GameRoom {
  return { ...room, log: [message, ...room.log].slice(0, 20) };
}

// ---------------------------------------------------------------------------
// Hand Evaluation — Fixed with tier-based scoring (A treated as rank 14)
// ---------------------------------------------------------------------------

const cardRank = (v: number): number => v === 1 ? 14 : v;

function vlabel(rank: number): string {
  if (rank === 14) return 'A';
  if (rank === 13) return 'K';
  if (rank === 12) return 'Q';
  if (rank === 11) return 'J';
  return String(rank);
}

// Each tier is 100000 apart; max composite for 3 cards (rank 2-14) using
// a * 225 + b * 15 + c ≤ 14*225+14*15+14 = 3374, well under 100000.
const TIER = { TRAIL: 500000, PURE_SEQ: 400000, SEQ: 300000, COLOR: 200000, PAIR: 100000 };
const composite = (a: number, b: number, c: number) => a * 225 + b * 15 + c;

export function evaluateHand(cards: Card[]): HandEval {
  if (cards.length !== 3) return { rank: 'high_card', score: 0, label: 'Invalid Hand' };

  const ranks = cards.map(c => cardRank(c.value));
  const suits = cards.map(c => c.suit);
  const sorted = [...ranks].sort((a, b) => b - a); // descending

  const isFlush = suits[0] === suits[1] && suits[1] === suits[2];
  const isTrail = sorted[0] === sorted[1] && sorted[1] === sorted[2];

  function isSeq(r: number[]): boolean {
    const asc = [...r].sort((a, b) => a - b);
    if (asc[2] - asc[1] === 1 && asc[1] - asc[0] === 1) return true;
    // A-2-3: ranks [14,2,3] → sorted [2,3,14]
    if (asc[0] === 2 && asc[1] === 3 && asc[2] === 14) return true;
    return false;
  }

  function seqHigh(r: number[]): number {
    const asc = [...r].sort((a, b) => a - b);
    // A-2-3 is lowest sequence
    if (asc[0] === 2 && asc[1] === 3 && asc[2] === 14) return 3;
    return asc[2];
  }

  if (isTrail) {
    return { rank: 'trail', score: TIER.TRAIL + sorted[0], label: `Trail of ${vlabel(sorted[0])}s` };
  }

  const isStraight = isSeq(sorted);

  if (isStraight && isFlush) {
    return {
      rank: 'pure_sequence',
      score: TIER.PURE_SEQ + seqHigh(sorted),
      label: `Pure Sequence (${sorted.map(vlabel).join('-')})`,
    };
  }

  if (isStraight) {
    return {
      rank: 'sequence',
      score: TIER.SEQ + seqHigh(sorted),
      label: `Sequence (${sorted.map(vlabel).join('-')})`,
    };
  }

  if (isFlush) {
    return {
      rank: 'color',
      score: TIER.COLOR + composite(sorted[0], sorted[1], sorted[2]),
      label: `Color (${sorted.map(vlabel).join('-')})`,
    };
  }

  // Pair
  let pairRank = -1, kickerRank = -1;
  if (sorted[0] === sorted[1])      { pairRank = sorted[0]; kickerRank = sorted[2]; }
  else if (sorted[1] === sorted[2]) { pairRank = sorted[1]; kickerRank = sorted[0]; }
  else if (sorted[0] === sorted[2]) { pairRank = sorted[0]; kickerRank = sorted[1]; }

  if (pairRank !== -1) {
    return {
      rank: 'pair',
      score: TIER.PAIR + pairRank * 100 + kickerRank,
      label: `Pair of ${vlabel(pairRank)}s`,
    };
  }

  return {
    rank: 'high_card',
    score: composite(sorted[0], sorted[1], sorted[2]),
    label: `High Card ${vlabel(sorted[0])}`,
  };
}

// ---------------------------------------------------------------------------
// Bot AI
// ---------------------------------------------------------------------------

function botDecide(player: GamePlayer, room: GameRoom): 'fold' | 'call' | 'raise' | 'show' {
  const hand = player.cards.length === 3 ? evaluateHand(player.cards) : null;
  const score = hand ? hand.score : 0;
  const style = player.botStyle ?? 'balanced';

  const isTrail   = score >= TIER.TRAIL;
  const isPureSeq = score >= TIER.PURE_SEQ && score < TIER.TRAIL;
  const isSeq     = score >= TIER.SEQ      && score < TIER.PURE_SEQ;
  const isColor   = score >= TIER.COLOR    && score < TIER.SEQ;
  const isPair    = score >= TIER.PAIR     && score < TIER.COLOR;

  const callAmount = player.status === 'seen'
    ? room.currentBet * 2 - player.currentBet
    : room.currentBet - player.currentBet;

  if (player.balance - callAmount < 100 && callAmount > 0) return 'fold';

  const rand = Math.random();
  const deviate = rand < 0.2;

  let decision: 'fold' | 'call' | 'raise' | 'show' = 'call';

  if (style === 'aggressive') {
    if (isTrail || isPureSeq)        decision = deviate ? 'call' : 'raise';
    else if (isSeq || isColor || isPair) decision = deviate ? 'fold' : 'raise';
    else                              decision = deviate ? 'fold' : 'call';
  } else if (style === 'conservative') {
    if (isTrail || isPureSeq)  decision = deviate ? 'call' : 'raise';
    else if (isSeq)            decision = deviate ? 'raise' : 'call';
    else if (isColor || isPair) decision = deviate ? 'fold' : 'call';
    else                        decision = deviate ? 'call' : 'fold';
  } else {
    if (isTrail || isPureSeq || isSeq) decision = deviate ? 'call' : 'raise';
    else if (isColor)                  decision = deviate ? 'raise' : 'call';
    else if (isPair)                   decision = deviate ? 'fold' : 'call';
    else                               decision = deviate ? 'call' : 'fold';
  }

  const active = room.players.filter(p => p.status !== 'folded');
  if (active.length === 2 && (isTrail || isPureSeq || isSeq) && Math.random() < 0.3) {
    decision = 'show';
  }

  return decision;
}

// ---------------------------------------------------------------------------
// Game helpers
// ---------------------------------------------------------------------------

function makeBot(seatIndex: number, usedNames: string[], startingBalance: number): GamePlayer {
  const available = BOT_ROSTER.filter(b => !usedNames.includes(b.name));
  const template = available.length > 0
    ? available[Math.floor(Math.random() * available.length)]
    : BOT_ROSTER[Math.floor(Math.random() * BOT_ROSTER.length)];

  return {
    id: `bot_${generateId()}`,
    name: template.name,
    photoURL: template.photoURL,
    balance: startingBalance,
    cards: [],
    currentBet: 0,
    totalBet: 0,
    status: 'waiting',
    isBot: true,
    isTurn: false,
    isDealer: false,
    seatIndex,
    botStyle: template.botStyle,
  };
}

function dealCards(room: GameRoom): GameRoom {
  const deck = createDeck();
  let cardIndex = 0;
  const count = room.players.length;
  const startIndex = (room.dealerIndex + 1) % count;
  const order: number[] = [];
  for (let i = 0; i < count; i++) order.push((startIndex + i) % count);

  const players = room.players.map(p => ({ ...p, cards: [] as Card[], currentBet: 0 }));

  for (let card = 0; card < 3; card++) {
    for (const idx of order) {
      players[idx].cards.push(deck[cardIndex++]);
    }
  }

  let pot = 0;
  for (let i = 0; i < players.length; i++) {
    const ante = Math.min(players[i].balance, room.bootAmount);
    players[i] = { ...players[i], balance: players[i].balance - ante, totalBet: ante, currentBet: 0, status: 'blind' };
    pot += ante;
  }

  const firstActive = order[0];
  players[firstActive] = { ...players[firstActive], isTurn: true };

  return { ...room, players, pot, currentBet: room.minBet, currentPlayerIndex: firstActive, previousPlayerIndex: firstActive, phase: 'betting' };
}

function activePlayers(room: GameRoom): GamePlayer[] {
  return room.players.filter(p => p.status !== 'folded');
}

function nextPlayerIndex(room: GameRoom, fromIndex: number): number {
  const count = room.players.length;
  for (let i = 1; i <= count; i++) {
    const idx = (fromIndex + i) % count;
    if (room.players[idx].status !== 'folded' && room.players[idx].status !== 'all_in') return idx;
  }
  return fromIndex;
}

function determineWinner(room: GameRoom): { winner: GamePlayer; hand: HandEval } {
  const active = activePlayers(room);
  let best: { player: GamePlayer; eval: HandEval } | null = null;

  for (const player of active) {
    if (player.cards.length === 3) {
      const ev = evaluateHand(player.cards);
      if (!best || ev.score > best.eval.score) best = { player, eval: ev };
    }
  }

  if (!best) return { winner: active[0], hand: { rank: 'high_card', score: 0, label: 'Default Win' } };
  return { winner: best.player, hand: best.eval };
}

function resolveWinner(room: GameRoom): GameRoom {
  const { winner, hand } = determineWinner(room);
  const players = room.players.map(p => p.id === winner.id ? { ...p, balance: p.balance + room.pot } : p);
  return addLog({ ...room, players, winner, winnerHand: hand, phase: 'round_over' }, `${winner.name} wins ₹${room.pot} with ${hand.label}!`);
}

function prepareNextRound(room: GameRoom): GameRoom {
  const newDealerIndex = (room.dealerIndex + 1) % room.players.length;
  const players = room.players
    .filter(p => p.balance > 0)
    .map((p, i) => ({ ...p, cards: [], currentBet: 0, totalBet: 0, status: 'waiting' as PlayerStatus, isTurn: false, isDealer: false, seatIndex: i }));

  const dealerIdx = newDealerIndex % players.length;
  if (players[dealerIdx]) players[dealerIdx] = { ...players[dealerIdx], isDealer: true };

  return { ...room, players, pot: 0, currentBet: room.minBet, phase: 'waiting', currentPlayerIndex: 0, previousPlayerIndex: 0, dealerIndex: dealerIdx, roundNumber: 0, winner: null, winnerHand: null, sideShowRequest: null };
}

// ---------------------------------------------------------------------------
// Seed rooms (pre-populated with bots so joinRoom works)
// ---------------------------------------------------------------------------

function makeSeededRoom(id: string, code: string, name: string, minBet: number, maxPlayers: number, botCount: number): GameRoom {
  const usedNames: string[] = [];
  const players: GamePlayer[] = [];

  for (let i = 0; i < botCount; i++) {
    const bot = makeBot(i, usedNames, 2000);
    usedNames.push(bot.name);
    players.push(bot);
  }

  const dealerIdx = 0;
  if (players[dealerIdx]) players[dealerIdx] = { ...players[dealerIdx], isDealer: true };

  return {
    id,
    code,
    name,
    players,
    minBet,
    pot: 0,
    currentBet: minBet,
    bootAmount: minBet,
    phase: 'waiting',
    currentPlayerIndex: 0,
    previousPlayerIndex: 0,
    dealerIndex: dealerIdx,
    roundNumber: 0,
    winner: null,
    winnerHand: null,
    maxPlayers,
    fillWithBots: true,
    log: [`${name} is waiting for players. Code: ${code}`],
    sideShowRequest: null,
  };
}

const INITIAL_LOBBY_ROOMS: LobbyRoom[] = [
  { id: 'lobby_seed1', code: 'FUN001', name: 'Desi Adda',      playerCount: 3, maxPlayers: 6, minBet: 10,  status: 'waiting' },
  { id: 'lobby_seed2', code: 'PRO420', name: 'High Rollers',   playerCount: 5, maxPlayers: 6, minBet: 100, status: 'playing' },
  { id: 'lobby_seed3', code: 'MID555', name: 'Friends Table',  playerCount: 2, maxPlayers: 4, minBet: 50,  status: 'waiting' },
];

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const GameContext = createContext<GameContextType | undefined>(undefined);
const LOCAL_PLAYER_ID = Math.random().toString(36).substr(2, 9);

export const GameProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [lobbyRooms, setLobbyRooms] = useState<LobbyRoom[]>(INITIAL_LOBBY_ROOMS);
  const [currentRoom, setCurrentRoom] = useState<GameRoom | null>(null);
  const roomsMapRef = useRef<Map<string, GameRoom>>(new Map());
  const botTimersRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  const localPlayerId = LOCAL_PLAYER_ID;

  // Initialize seed rooms in roomsMapRef so joinRoom works
  useEffect(() => {
    const seed1 = makeSeededRoom('lobby_seed1', 'FUN001', 'Desi Adda',    10,  6, 3);
    const seed2 = makeSeededRoom('lobby_seed2', 'PRO420', 'High Rollers', 100, 6, 5);
    const seed3 = makeSeededRoom('lobby_seed3', 'MID555', 'Friends Table', 50, 4, 2);
    roomsMapRef.current.set(seed1.id, seed1);
    roomsMapRef.current.set(seed2.id, seed2);
    roomsMapRef.current.set(seed3.id, seed3);
  }, []);

  const clearBotTimers = useCallback(() => {
    botTimersRef.current.forEach(t => clearTimeout(t));
    botTimersRef.current = [];
  }, []);

  useEffect(() => { return () => clearBotTimers(); }, [clearBotTimers]);

  // ---------------------------------------------------------------------------
  // Pure action helpers
  // ---------------------------------------------------------------------------

  function advanceTurn(room: GameRoom): GameRoom {
    const active = activePlayers(room);
    if (active.length <= 1) return resolveWinner(room);

    const allBetsEqual = active.every(p => {
      const expected = p.status === 'seen' ? room.currentBet * 2 : room.currentBet;
      return p.currentBet >= expected;
    });

    const newRoundNumber = allBetsEqual ? room.roundNumber + 1 : room.roundNumber;

    if (allBetsEqual && newRoundNumber >= 3) return resolveWinner({ ...room, roundNumber: newRoundNumber });

    let updated = { ...room, roundNumber: newRoundNumber };
    if (allBetsEqual) {
      updated = { ...updated, players: updated.players.map(p => ({ ...p, currentBet: 0 })) };
    }

    const oldIndex = updated.currentPlayerIndex;
    const cleared = updated.players.map(p => ({ ...p, isTurn: false }));
    updated = { ...updated, players: cleared };

    const nextIndex = nextPlayerIndex(updated, oldIndex);
    const nextPlayers = updated.players.map((p, i) => i === nextIndex ? { ...p, isTurn: true } : p);

    return { ...updated, players: nextPlayers, previousPlayerIndex: oldIndex, currentPlayerIndex: nextIndex };
  }

  function applyFold(room: GameRoom, playerIndex: number): GameRoom {
    const players = room.players.map((p, i) =>
      i === playerIndex ? { ...p, status: 'folded' as PlayerStatus, isTurn: false } : p
    );
    return advanceTurn(addLog({ ...room, players }, `${room.players[playerIndex].name} folded.`));
  }

  function applyCall(room: GameRoom, playerIndex: number): GameRoom {
    const player = room.players[playerIndex];
    const expected = player.status === 'seen' ? room.currentBet * 2 : room.currentBet;
    const needed = Math.max(0, expected - player.currentBet);
    const actual = Math.min(needed, player.balance);
    const newStatus: PlayerStatus = player.balance - actual <= 0 ? 'all_in' : player.status;

    const players = room.players.map((p, i) =>
      i === playerIndex
        ? { ...p, balance: p.balance - actual, currentBet: p.currentBet + actual, totalBet: p.totalBet + actual, status: newStatus, isTurn: false }
        : p
    );
    return advanceTurn(addLog({ ...room, players, pot: room.pot + actual }, `${player.name} called ₹${actual}.`));
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
    return advanceTurn(addLog({ ...room, players, pot: room.pot + raiseAmount, currentBet: newCurrentBet }, `${player.name} raised by ₹${raiseAmount}.`));
  }

  function applyShowdown(room: GameRoom): GameRoom {
    return resolveWinner({ ...room, phase: 'showdown' });
  }

  function applyRequestSideShow(room: GameRoom, playerIndex: number): GameRoom {
    const active = activePlayers(room);
    if (active.length < 3) return room; // need 3+ active; use show with 2

    const requester = room.players[playerIndex];
    if (requester.status !== 'seen') return room;

    const target = room.players[room.previousPlayerIndex];
    if (!target || target.status === 'folded' || target.status !== 'seen') return room;
    if (target.id === requester.id) return room;

    return addLog({ ...room, sideShowRequest: { requesterId: requester.id, targetId: target.id } },
      `${requester.name} requested a side show from ${target.name}.`);
  }

  function applyRespondSideShow(room: GameRoom, accept: boolean): GameRoom {
    const req = room.sideShowRequest;
    if (!req) return room;

    let updated = { ...room, sideShowRequest: null };

    if (accept) {
      const reqPlayer = updated.players.find(p => p.id === req.requesterId);
      const tgtPlayer = updated.players.find(p => p.id === req.targetId);
      if (reqPlayer && tgtPlayer && reqPlayer.cards.length === 3 && tgtPlayer.cards.length === 3) {
        const reqEval = evaluateHand(reqPlayer.cards);
        const tgtEval = evaluateHand(tgtPlayer.cards);
        const loser = reqEval.score >= tgtEval.score ? tgtPlayer : reqPlayer;
        const loserIdx = updated.players.findIndex(p => p.id === loser.id);
        updated = addLog(updated, `Side show: ${loser.name} loses and folds.`);
        return applyFold(updated, loserIdx);
      }
    }

    updated = addLog(updated, `Side show refused. Play continues.`);
    return advanceTurn(updated);
  }

  // ---------------------------------------------------------------------------
  // Bot auto-play
  // ---------------------------------------------------------------------------

  const scheduleBotTurn = useCallback((room: GameRoom) => {
    const currentPlayer = room.players[room.currentPlayerIndex];
    if (!currentPlayer?.isBot || room.phase !== 'betting') return;

    const delay = 1500 + Math.random() * 1000;
    const timer = setTimeout(() => {
      setCurrentRoom(prev => {
        if (!prev) return prev;

        // Handle bot responding to a sideshow request targeting them
        if (prev.sideShowRequest?.targetId === currentPlayer.id) {
          const hand = evaluateHand(currentPlayer.cards);
          const accept = hand.score >= TIER.SEQ; // strong hands accept
          const updated = applyRespondSideShow(prev, accept);
          roomsMapRef.current.set(updated.id, updated);
          return updated;
        }

        const bot = prev.players[prev.currentPlayerIndex];
        if (!bot?.isBot) return prev;

        let updatedRoom = { ...prev };

        // Bots may look at cards (40% chance)
        if (bot.status === 'blind' && Math.random() < 0.4) {
          updatedRoom = { ...updatedRoom, players: updatedRoom.players.map((p, i) =>
            i === updatedRoom.currentPlayerIndex ? { ...p, status: 'seen' as PlayerStatus } : p
          )};
        }

        const freshBot = updatedRoom.players[updatedRoom.currentPlayerIndex];
        const decision = botDecide(freshBot, updatedRoom);

        if (decision === 'fold') updatedRoom = applyFold(updatedRoom, updatedRoom.currentPlayerIndex);
        else if (decision === 'raise') updatedRoom = applyRaise(updatedRoom, updatedRoom.currentPlayerIndex, updatedRoom.minBet * 2);
        else if (decision === 'show') updatedRoom = applyShowdown(updatedRoom);
        else updatedRoom = applyCall(updatedRoom, updatedRoom.currentPlayerIndex);

        roomsMapRef.current.set(updatedRoom.id, updatedRoom);
        return updatedRoom;
      });
    }, delay);

    botTimersRef.current.push(timer);
  }, []);

  useEffect(() => {
    if (!currentRoom) return;
    const cp = currentRoom.players[currentRoom.currentPlayerIndex];
    if (cp?.isBot && currentRoom.phase === 'betting') scheduleBotTurn(currentRoom);

    // Bot responds to sideshow request aimed at it
    if (currentRoom.sideShowRequest) {
      const target = currentRoom.players.find(p => p.id === currentRoom.sideShowRequest?.targetId);
      if (target?.isBot) {
        const delay = 1200 + Math.random() * 800;
        const timer = setTimeout(() => {
          setCurrentRoom(prev => {
            if (!prev?.sideShowRequest) return prev;
            const hand = evaluateHand(target.cards);
            const accept = hand.score >= TIER.SEQ;
            const updated = applyRespondSideShow(prev, accept);
            roomsMapRef.current.set(updated.id, updated);
            return updated;
          });
        }, delay);
        botTimersRef.current.push(timer);
      }
    }
  }, [currentRoom?.currentPlayerIndex, currentRoom?.phase, currentRoom?.sideShowRequest, scheduleBotTurn]);

  useEffect(() => {
    if (currentRoom?.phase !== 'round_over') return;
    const timer = setTimeout(() => {
      setCurrentRoom(prev => {
        if (!prev || prev.phase !== 'round_over') return prev;
        const next = prepareNextRound(prev);
        roomsMapRef.current.set(next.id, next);
        return next;
      });
    }, 3500);
    botTimersRef.current.push(timer);
    return () => clearTimeout(timer);
  }, [currentRoom?.phase, currentRoom?.roundNumber]);

  // ---------------------------------------------------------------------------
  // Lobby actions
  // ---------------------------------------------------------------------------

  const createRoom = useCallback((name: string, minBet: number, maxPlayers: number, fillWithBots: boolean) => {
    const roomId = `room_${generateId()}`;
    const code = generateRoomCode();

    const localPlayer: GamePlayer = {
      id: localPlayerId,
      name: 'You',
      photoURL: `https://ui-avatars.com/api/?name=You&background=f59e0b&color=000`,
      balance: 5000,
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
    const usedNames: string[] = [];

    if (fillWithBots) {
      for (let i = 0; i < maxPlayers - 1; i++) {
        const bot = makeBot(i + 1, usedNames, 2000);
        usedNames.push(bot.name);
        players.push(bot);
      }
    }

    const dealerIdx = players.length > 1 ? 1 : 0;
    players[dealerIdx] = { ...players[dealerIdx], isDealer: true };

    const newRoom: GameRoom = {
      id: roomId, code, name, players, minBet,
      pot: 0, currentBet: minBet, bootAmount: minBet,
      phase: 'waiting', currentPlayerIndex: 0, previousPlayerIndex: 0,
      dealerIndex: dealerIdx, roundNumber: 0,
      winner: null, winnerHand: null,
      maxPlayers, fillWithBots,
      log: [`Room "${name}" created. Code: ${code}`],
      sideShowRequest: null,
    };

    roomsMapRef.current.set(roomId, newRoom);
    setLobbyRooms(prev => [{ id: roomId, code, name, playerCount: players.length, maxPlayers, minBet, status: 'waiting' }, ...prev]);
    setCurrentRoom(newRoom);
  }, [localPlayerId]);

  const joinRoom = useCallback((roomId: string) => {
    const room = roomsMapRef.current.get(roomId);
    if (!room) return;
    if (room.players.find(p => p.id === localPlayerId)) { setCurrentRoom(room); return; }
    if (room.players.length >= room.maxPlayers) return;

    const newPlayer: GamePlayer = {
      id: localPlayerId,
      name: 'You',
      photoURL: `https://ui-avatars.com/api/?name=You&background=f59e0b&color=000`,
      balance: 5000,
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
      if (room.code === upper) { joinRoom(id); return true; }
    }
    return false;
  }, [joinRoom]);

  const leaveRoom = useCallback(() => {
    clearBotTimers();
    setCurrentRoom(null);
  }, [clearBotTimers]);

  const addBot = useCallback((seatIndex: number) => {
    setCurrentRoom(prev => {
      if (!prev || prev.players.length >= prev.maxPlayers) return prev;
      const usedNames = prev.players.map(p => p.name);
      const bot = makeBot(seatIndex, usedNames, 2000);
      const updated = { ...prev, players: [...prev.players, bot] };
      roomsMapRef.current.set(updated.id, updated);
      return updated;
    });
  }, []);

  const startGame = useCallback(() => {
    setCurrentRoom(prev => {
      if (!prev || prev.players.length < 2) return prev;
      clearBotTimers();

      const dealing: GameRoom = addLog({ ...prev, phase: 'dealing' }, 'Dealing cards...');
      const dealt = dealCards(dealing);
      const preDealt: GameRoom = { ...dealt, phase: 'dealing' };

      const timer = setTimeout(() => {
        setCurrentRoom(r => {
          if (!r || r.phase !== 'dealing') return r;
          const betting = addLog({ ...r, phase: 'betting' }, 'Betting begins!');
          roomsMapRef.current.set(betting.id, betting);
          return betting;
        });
      }, 1800);
      botTimersRef.current.push(timer);

      roomsMapRef.current.set(preDealt.id, preDealt);
      return preDealt;
    });
  }, [clearBotTimers]);

  // ---------------------------------------------------------------------------
  // Game actions (player)
  // ---------------------------------------------------------------------------

  const callBet = useCallback(() => {
    setCurrentRoom(prev => {
      if (!prev || prev.phase !== 'betting') return prev;
      const idx = prev.players.findIndex(p => p.id === localPlayerId);
      if (idx === -1 || !prev.players[idx].isTurn) return prev;
      const updated = applyCall(prev, idx);
      roomsMapRef.current.set(updated.id, updated);
      return updated;
    });
  }, [localPlayerId]);

  const raiseBet = useCallback((amount: number) => {
    setCurrentRoom(prev => {
      if (!prev || prev.phase !== 'betting') return prev;
      const idx = prev.players.findIndex(p => p.id === localPlayerId);
      if (idx === -1 || !prev.players[idx].isTurn) return prev;
      const updated = applyRaise(prev, idx, amount);
      roomsMapRef.current.set(updated.id, updated);
      return updated;
    });
  }, [localPlayerId]);

  const foldHand = useCallback(() => {
    setCurrentRoom(prev => {
      if (!prev || prev.phase !== 'betting') return prev;
      const idx = prev.players.findIndex(p => p.id === localPlayerId);
      if (idx === -1 || !prev.players[idx].isTurn) return prev;
      const updated = applyFold(prev, idx);
      roomsMapRef.current.set(updated.id, updated);
      return updated;
    });
  }, [localPlayerId]);

  const showCards = useCallback(() => {
    setCurrentRoom(prev => {
      if (!prev || prev.phase !== 'betting') return prev;
      const idx = prev.players.findIndex(p => p.id === localPlayerId);
      if (idx === -1 || !prev.players[idx].isTurn) return prev;
      // Show only allowed when seen
      if (prev.players[idx].status !== 'seen') return prev;
      const updated = applyShowdown(prev);
      roomsMapRef.current.set(updated.id, updated);
      return updated;
    });
  }, [localPlayerId]);

  const seeCards = useCallback(() => {
    setCurrentRoom(prev => {
      if (!prev) return prev;
      const idx = prev.players.findIndex(p => p.id === localPlayerId);
      if (idx === -1 || prev.players[idx].status !== 'blind') return prev;
      const players = prev.players.map((p, i) => i === idx ? { ...p, status: 'seen' as PlayerStatus } : p);
      const updated = addLog({ ...prev, players }, 'You looked at your cards.');
      roomsMapRef.current.set(updated.id, updated);
      return updated;
    });
  }, [localPlayerId]);

  // Fixed: playBlind now actually calls the bet while keeping status as 'blind'
  const playBlind = useCallback(() => {
    setCurrentRoom(prev => {
      if (!prev || prev.phase !== 'betting') return prev;
      const idx = prev.players.findIndex(p => p.id === localPlayerId);
      if (idx === -1 || !prev.players[idx].isTurn || prev.players[idx].status !== 'blind') return prev;
      const updated = applyCall(prev, idx);
      roomsMapRef.current.set(updated.id, updated);
      return updated;
    });
  }, [localPlayerId]);

  const requestSideShow = useCallback(() => {
    setCurrentRoom(prev => {
      if (!prev || prev.phase !== 'betting') return prev;
      const idx = prev.players.findIndex(p => p.id === localPlayerId);
      if (idx === -1 || !prev.players[idx].isTurn) return prev;
      const updated = applyRequestSideShow(prev, idx);
      roomsMapRef.current.set(updated.id, updated);
      return updated;
    });
  }, [localPlayerId]);

  const respondSideShow = useCallback((accept: boolean) => {
    setCurrentRoom(prev => {
      if (!prev?.sideShowRequest) return prev;
      if (prev.sideShowRequest.targetId !== localPlayerId) return prev;
      const updated = applyRespondSideShow(prev, accept);
      roomsMapRef.current.set(updated.id, updated);
      return updated;
    });
  }, [localPlayerId]);

  // ---------------------------------------------------------------------------
  // Derived
  // ---------------------------------------------------------------------------

  const localPlayer = currentRoom?.players.find(p => p.id === localPlayerId) ?? null;
  const isLocalPlayerTurn = localPlayer?.isTurn ?? false;

  const value: GameContextType = {
    lobbyRooms, currentRoom, localPlayerId,
    createRoom, joinRoom, joinRoomByCode, leaveRoom,
    callBet, raiseBet, foldHand, showCards, seeCards, playBlind,
    requestSideShow, respondSideShow,
    startGame, addBot,
    localPlayer, isLocalPlayerTurn,
  };

  return <GameContext.Provider value={value}>{children}</GameContext.Provider>;
};

export const useGame = (): GameContextType => {
  const context = useContext(GameContext);
  if (context === undefined) throw new Error('useGame must be used within a GameProvider');
  return context;
};
