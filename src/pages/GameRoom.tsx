import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useGame, GamePlayer, Card, evaluateHand } from '@/contexts/GameContext';
import { useAuth } from '@/contexts/AuthContext';
import { useToast } from '@/hooks/use-toast';

// ─── Card helpers ────────────────────────────────────────────────────────────
const SUIT_SYM: Record<string, string> = { hearts: '♥', diamonds: '♦', clubs: '♣', spades: '♠' };
const IS_RED = (s: string) => s === 'hearts' || s === 'diamonds';
const cardLabel = (v: number) => v === 1 ? 'A' : v === 11 ? 'J' : v === 12 ? 'Q' : v === 13 ? 'K' : String(v);

// ─── PlayingCard ─────────────────────────────────────────────────────────────
interface CardProps { card?: Card; faceDown?: boolean; delay?: number; animate?: boolean; size?: 'sm' | 'md' | 'lg'; }

const PlayingCard: React.FC<CardProps> = ({ card, faceDown = false, delay = 0, animate = false, size = 'md' }) => {
  const [visible, setVisible] = useState(false);
  const [flipped, setFlipped] = useState(false);

  useEffect(() => {
    if (!animate) return;
    const t = setTimeout(() => setVisible(true), delay);
    return () => clearTimeout(t);
  }, [animate, delay]);

  useEffect(() => {
    if (visible && !faceDown) {
      const t = setTimeout(() => setFlipped(true), 350);
      return () => clearTimeout(t);
    }
    if (faceDown) setFlipped(false);
  }, [visible, faceDown]);

  const dims = size === 'lg' ? { w: 68, h: 96 } : size === 'sm' ? { w: 36, h: 52 } : { w: 52, h: 74 };

  return (
    <div
      className={`transition-all duration-500 ${visible ? 'card-deal-up opacity-100' : 'opacity-0 scale-75'}`}
      style={{ width: dims.w, height: dims.h, flexShrink: 0, perspective: 800, animationDelay: `${delay}ms` }}
    >
      <div style={{ width: '100%', height: '100%', transformStyle: 'preserve-3d', transition: 'transform 0.45s ease', transform: flipped ? 'rotateY(180deg)' : 'rotateY(0deg)', position: 'relative' }}>
        {/* Back */}
        <div className="absolute inset-0 rounded-lg shadow-2xl overflow-hidden" style={{ backfaceVisibility: 'hidden', WebkitBackfaceVisibility: 'hidden' }}>
          <div className="w-full h-full flex items-center justify-center" style={{ background: 'linear-gradient(135deg,#1a3a8f,#0d2260)', border: '2px solid rgba(255,255,255,0.15)', borderRadius: 8 }}>
            <div style={{ width: '82%', height: '82%', border: '1px solid rgba(100,149,237,0.35)', borderRadius: 4, backgroundImage: 'repeating-linear-gradient(45deg,rgba(255,255,255,0.03) 0px,rgba(255,255,255,0.03) 1px,transparent 1px,transparent 7px)' }} />
          </div>
        </div>
        {/* Front */}
        <div className="absolute inset-0 rounded-lg shadow-2xl bg-white overflow-hidden" style={{ backfaceVisibility: 'hidden', WebkitBackfaceVisibility: 'hidden', transform: 'rotateY(180deg)', border: '1px solid #e5e7eb' }}>
          {card && (
            <div className="w-full h-full flex flex-col" style={{ color: IS_RED(card.suit) ? '#dc2626' : '#111', padding: size === 'sm' ? 3 : 5 }}>
              <div style={{ lineHeight: 1 }}>
                <div style={{ fontWeight: 800, fontSize: size === 'sm' ? 9 : size === 'lg' ? 15 : 12 }}>{cardLabel(card.value)}</div>
                <div style={{ fontSize: size === 'sm' ? 8 : size === 'lg' ? 13 : 11 }}>{SUIT_SYM[card.suit]}</div>
              </div>
              <div className="flex-1 flex items-center justify-center" style={{ fontSize: size === 'sm' ? 18 : size === 'lg' ? 36 : 28 }}>{SUIT_SYM[card.suit]}</div>
              <div style={{ lineHeight: 1, alignSelf: 'flex-end', transform: 'rotate(180deg)' }}>
                <div style={{ fontWeight: 800, fontSize: size === 'sm' ? 9 : size === 'lg' ? 15 : 12 }}>{cardLabel(card.value)}</div>
                <div style={{ fontSize: size === 'sm' ? 8 : size === 'lg' ? 13 : 11 }}>{SUIT_SYM[card.suit]}</div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// ─── Chip badge ───────────────────────────────────────────────────────────────
const Chip: React.FC<{ amount: number; className?: string }> = ({ amount, className = '' }) => (
  <div className={`flex items-center gap-1 rounded-full px-2 py-0.5 ${className}`} style={{ background: 'rgba(0,0,0,0.6)', border: '1px solid rgba(212,175,55,0.45)' }}>
    <div className="w-3 h-3 rounded-full bg-yellow-400 border border-yellow-600 flex-shrink-0" />
    <span className="text-yellow-300 font-bold" style={{ fontSize: 11 }}>₹{amount.toLocaleString()}</span>
  </div>
);

// ─── Status pill ──────────────────────────────────────────────────────────────
const StatusPill: React.FC<{ status: string }> = ({ status }) => {
  const cfg: Record<string, { label: string; color: string; bg: string }> = {
    blind:  { label: 'BLIND',  color: '#93c5fd', bg: 'rgba(30,64,175,0.4)' },
    seen:   { label: 'SEEN',   color: '#86efac', bg: 'rgba(22,101,52,0.4)' },
    folded: { label: 'FOLDED', color: '#fca5a5', bg: 'rgba(153,27,27,0.4)' },
    all_in: { label: 'ALL-IN', color: '#fde68a', bg: 'rgba(120,53,15,0.5)' },
    waiting:{ label: 'WAIT',   color: '#d1d5db', bg: 'rgba(75,85,99,0.4)'  },
  };
  const c = cfg[status] || cfg.waiting;
  return (
    <span className="text-xs font-bold px-1.5 py-0.5 rounded-full" style={{ color: c.color, background: c.bg, fontSize: 9 }}>{c.label}</span>
  );
};

// ─── Seat positions around oval ───────────────────────────────────────────────
// Returns CSS position props for each seatIndex (0 = user/bottom-center)
function seatPosition(seatIndex: number, total: number): React.CSSProperties {
  // Predefined positions for up to 6 seats, laid out around the oval
  const positions: React.CSSProperties[] = [
    { bottom: '4%',  left: '50%',  transform: 'translateX(-50%)' }, // 0: user bottom
    { bottom: '18%', right: '4%'  },                                  // 1: bottom-right
    { top: '18%',    right: '4%'  },                                  // 2: top-right
    { top: '4%',     left: '50%',  transform: 'translateX(-50%)' }, // 3: top-center
    { top: '18%',    left: '4%'  },                                   // 4: top-left
    { bottom: '18%', left: '4%'  },                                   // 5: bottom-left
  ];
  return { position: 'absolute', ...positions[seatIndex] };
}

// ─── Player Seat ──────────────────────────────────────────────────────────────
interface SeatProps {
  player: GamePlayer;
  isLocal: boolean;
  animate: boolean;
  dealBaseDelay: number;
  showCards: boolean;
}

const PlayerSeatComponent: React.FC<SeatProps> = ({ player, isLocal, animate, dealBaseDelay, showCards }) => {
  const folded = player.status === 'folded';
  const isTurn = player.isTurn;
  const handEval = isLocal && showCards && player.cards.length === 3 ? evaluateHand(player.cards) : null;

  return (
    <div className={`flex flex-col items-center gap-1 transition-opacity duration-500 ${folded ? 'opacity-30' : ''}`}>
      {/* Cards */}
      {player.cards.length > 0 && (
        <div className="flex gap-1">
          {player.cards.map((card, i) => (
            <PlayingCard
              key={i}
              card={card}
              faceDown={!isLocal || !showCards}
              animate={animate}
              delay={dealBaseDelay + i * 350}
              size={isLocal ? 'lg' : 'sm'}
            />
          ))}
        </div>
      )}
      {player.cards.length === 0 && !folded && (
        <div className="flex gap-1">
          {[0,1,2].map(i => (
            <div key={i} className="rounded-lg bg-white/5 border border-white/10" style={{ width: isLocal ? 68 : 36, height: isLocal ? 96 : 52 }} />
          ))}
        </div>
      )}

      {/* Hand rank label for local player */}
      {handEval && (
        <div className="text-xs font-black tracking-wider px-2 py-0.5 rounded-full" style={{ background: 'rgba(212,175,55,0.2)', color: '#fbbf24', border: '1px solid rgba(212,175,55,0.4)', fontSize: 10 }}>
          {handEval.label.toUpperCase()}
        </div>
      )}

      {/* Seat info card */}
      <div
        className={`flex flex-col items-center gap-1 rounded-xl px-2 py-1.5 ${isTurn ? 'turn-glow' : ''}`}
        style={{ background: 'rgba(0,0,0,0.65)', backdropFilter: 'blur(8px)', border: isTurn ? '1px solid rgba(250,204,21,0.8)' : '1px solid rgba(255,255,255,0.1)', minWidth: 72 }}
      >
        <div className="relative rounded-full overflow-hidden" style={{ width: isLocal ? 46 : 38, height: isLocal ? 46 : 38, border: isTurn ? '2px solid #facc15' : `2px solid ${isLocal ? '#d4af37' : 'rgba(255,255,255,0.25)'}` }}>
          <img src={player.photoURL} alt={player.name} className="w-full h-full object-cover" />
          {isTurn && <div className="absolute inset-0 bg-yellow-300/15 animate-pulse" />}
        </div>
        <span className="text-white font-semibold truncate" style={{ fontSize: 11, maxWidth: 72 }}>{player.name}</span>
        <Chip amount={player.balance} />
        <div className="flex items-center gap-1">
          <StatusPill status={player.status} />
          {player.isDealer && <span className="w-4 h-4 rounded-full bg-white text-black flex items-center justify-center font-black" style={{ fontSize: 9 }}>D</span>}
        </div>
        {player.currentBet > 0 && (
          <span className="text-yellow-300 font-semibold" style={{ fontSize: 10 }}>Bet ₹{player.currentBet}</span>
        )}
      </div>
    </div>
  );
};

// ─── GameRoom ─────────────────────────────────────────────────────────────────
const GameRoom: React.FC = () => {
  const { currentRoom, localPlayerId, localPlayer, isLocalPlayerTurn, callBet, raiseBet, foldHand, showCards: showCardsAction, seeCards, playBlind, startGame, leaveRoom } = useGame();
  const { user } = useAuth();
  const navigate = useNavigate();
  const { toast } = useToast();

  const [raiseAmount, setRaiseAmount] = useState(0);
  const [showLeave, setShowLeave] = useState(false);
  const [cardsVisible, setCardsVisible] = useState(false);
  const [localCardsRevealed, setLocalCardsRevealed] = useState(false);
  const [codeCopied, setCodeCopied] = useState(false);
  const prevPhase = useRef<string>('');
  const animateRef = useRef(false);

  useEffect(() => {
    if (!currentRoom) { navigate('/lobby'); return; }
    setRaiseAmount(currentRoom.minBet * 2);
  }, []);

  // Trigger deal animation when phase moves to dealing
  useEffect(() => {
    if (!currentRoom) return;
    if (currentRoom.phase === 'dealing' && prevPhase.current !== 'dealing') {
      animateRef.current = true;
      setCardsVisible(true);
      setLocalCardsRevealed(false);
    }
    if (currentRoom.phase === 'betting' && prevPhase.current === 'dealing') {
      // Reveal local player cards after dealing
      setTimeout(() => setLocalCardsRevealed(true), 600);
    }
    if (currentRoom.phase === 'waiting') {
      setCardsVisible(false);
      setLocalCardsRevealed(false);
      animateRef.current = false;
    }
    prevPhase.current = currentRoom.phase;
  }, [currentRoom?.phase]);

  if (!currentRoom) return null;

  const phase = currentRoom.phase;
  const players = currentRoom.players;
  const isHost = players[0]?.id === localPlayerId;

  const handleCopyCode = () => {
    navigator.clipboard.writeText(currentRoom.code).catch(() => {});
    setCodeCopied(true);
    setTimeout(() => setCodeCopied(false), 2000);
  };

  const handleSee = () => { seeCards(); setLocalCardsRevealed(true); };
  const handleFold = () => { foldHand(); toast({ title: 'You folded.' }); };
  const handleCall = () => { callBet(); toast({ title: `Called ₹${currentRoom.currentBet}` }); };
  const handleRaise = () => { raiseBet(raiseAmount); toast({ title: `Raised to ₹${raiseAmount}` }); };
  const handleShow = () => { showCardsAction(); };

  // Dealing delay: round-robin across seats
  // seat i, card j → delay = (j * players.length + i) * 350ms
  const getDealDelay = (seatIndex: number, cardIndex = 0) => (cardIndex * players.length + seatIndex) * 350;

  return (
    <div className="min-h-screen flex flex-col select-none overflow-hidden" style={{ background: 'radial-gradient(ellipse at 50% 30%,#1a0d3a,#0a0618 65%,#000)' }}>
      <div className="h-0.5 flex-shrink-0" style={{ background: 'linear-gradient(90deg,transparent,#d4af37,#f0d060,#d4af37,transparent)' }} />

      {/* ── Header ── */}
      <header className="flex items-center justify-between px-4 py-2 flex-shrink-0" style={{ background: 'rgba(0,0,0,0.55)', backdropFilter: 'blur(10px)', borderBottom: '1px solid rgba(212,175,55,0.12)' }}>
        <div className="flex items-center gap-2 min-w-0">
          <span className="gold-text font-black tracking-wider text-base hidden sm:block" style={{ fontFamily: 'Georgia,serif' }}>TEEN PATTI</span>
          <span className="text-white/30 hidden sm:block">|</span>
          <span className="text-white/70 text-sm font-semibold truncate">{currentRoom.name}</span>
        </div>

        {/* Room code */}
        <button onClick={handleCopyCode} className="flex items-center gap-1.5 px-3 py-1 rounded-lg transition-all" style={{ background: 'rgba(212,175,55,0.1)', border: '1px solid rgba(212,175,55,0.3)' }}>
          <span className="text-yellow-400 font-black tracking-widest text-sm">{currentRoom.code}</span>
          <span className="text-yellow-600 text-xs">{codeCopied ? '✓' : '📋'}</span>
        </button>

        <div className="flex items-center gap-3">
          <Chip amount={localPlayer?.balance ?? user?.balance ?? 0} />
          <button onClick={() => setShowLeave(true)} className="px-3 py-1.5 rounded-lg text-sm font-bold text-white/80 hover:text-white transition-colors" style={{ background: 'rgba(185,28,28,0.3)', border: '1px solid rgba(185,28,28,0.4)' }}>
            Leave
          </button>
        </div>
      </header>

      {/* ── Main game area ── */}
      <div className="flex-1 relative flex items-center justify-center overflow-hidden py-2">
        {/* Seats container — positioned relative to center */}
        <div className="relative" style={{ width: 'min(860px, 98vw)', height: 'min(520px, 92vh)' }}>

          {/* Player seats */}
          {players.map((player) => (
            <div key={player.id} style={seatPosition(player.seatIndex, players.length)}>
              <PlayerSeatComponent
                player={player}
                isLocal={player.id === localPlayerId}
                animate={cardsVisible}
                dealBaseDelay={getDealDelay(player.seatIndex)}
                showCards={localCardsRevealed}
              />
            </div>
          ))}

          {/* ── Oval poker table ── */}
          <div
            className="absolute table-felt"
            style={{
              width: 'min(560px,70vw)', height: 'min(200px,28vw)', minHeight: 130,
              top: '50%', left: '50%', transform: 'translate(-50%,-50%)',
              borderRadius: '50%',
              border: '18px solid #4a2200',
              boxShadow: '0 0 0 3px #7a4810,0 0 0 5px #3d1a00,inset 0 0 60px rgba(0,0,0,0.5),0 25px 70px rgba(0,0,0,0.8)',
              zIndex: 0,
            }}
          >
            {/* Gold inner rail */}
            <div className="absolute inset-2 rounded-[50%] pointer-events-none" style={{ border: '1px solid rgba(212,175,55,0.2)' }} />

            {/* Table center content */}
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-1 z-10">
              {/* Pot */}
              <div className="flex items-center gap-2 rounded-full px-4 py-1.5 pot-pulse" style={{ background: 'rgba(0,0,0,0.65)', border: '1px solid rgba(212,175,55,0.45)', backdropFilter: 'blur(4px)' }}>
                <div className="flex">
                  {['#e53e3e','#d4af37','#3182ce'].map((c,i) => (
                    <div key={i} className="w-5 h-5 rounded-full border-2" style={{ background: c, borderColor: c, marginLeft: i > 0 ? -7 : 0, zIndex: 3-i }} />
                  ))}
                </div>
                <span className="text-yellow-300 font-bold text-sm">POT ₹{currentRoom.pot.toLocaleString()}</span>
              </div>

              {/* Game log */}
              <div className="flex flex-col items-center gap-0.5 max-w-[200px]">
                {currentRoom.log.slice(-2).map((entry, i) => (
                  <span key={i} className="text-white/40 text-center" style={{ fontSize: 9 }}>{entry}</span>
                ))}
              </div>

              {/* Round */}
              {phase === 'betting' && (
                <span className="text-white/30" style={{ fontSize: 9 }}>Round {currentRoom.roundNumber} • Bet ₹{currentRoom.currentBet}</span>
              )}
            </div>

            {/* Dealer button on table edge */}
            <div className="absolute right-[10%] top-1/2 -translate-y-1/2 w-6 h-6 rounded-full flex items-center justify-center font-black" style={{ background: 'white', border: '2px solid #d4af37', color: '#111', fontSize: 10, boxShadow: '0 2px 8px rgba(0,0,0,0.5)' }}>D</div>
          </div>

          {/* Deck visual at center (shown during dealing) */}
          {phase === 'dealing' && (
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-20 pointer-events-none" style={{ marginTop: -20 }}>
              {[0,1,2,3,4].map(i => (
                <div key={i} className="absolute rounded-lg" style={{ width: 42, height: 60, background: 'linear-gradient(135deg,#1a3a8f,#0d2260)', border: '1px solid rgba(255,255,255,0.2)', top: -i*1.5, left: -i*0.5, boxShadow: '0 4px 12px rgba(0,0,0,0.5)' }} />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── Round over overlay ── */}
      {phase === 'round_over' && currentRoom.winner && (
        <div className="fixed inset-0 z-40 flex items-center justify-center pointer-events-none" style={{ background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)' }}>
          <div className="flex flex-col items-center gap-4 px-10 py-8 rounded-2xl scale-in" style={{ background: 'linear-gradient(135deg,#1a0d3a,#100820)', border: '1px solid rgba(212,175,55,0.4)', boxShadow: '0 0 60px rgba(212,175,55,0.2)' }}>
            <div className="text-yellow-400 font-black text-2xl tracking-wider">🏆 WINNER!</div>
            <div className="flex items-center gap-3">
              <img src={currentRoom.winner.photoURL} alt={currentRoom.winner.name} className="w-14 h-14 rounded-full border-2 border-yellow-400" />
              <div>
                <p className="text-white font-bold text-lg">{currentRoom.winner.name}</p>
                <p className="text-yellow-400 font-semibold">{currentRoom.winnerHand?.label}</p>
                <p className="text-green-400 font-bold">+₹{currentRoom.pot.toLocaleString()}</p>
              </div>
            </div>
            <p className="text-white/40 text-sm">Next round starting soon…</p>
          </div>
        </div>
      )}

      {/* ── Dealing overlay ── */}
      {phase === 'dealing' && (
        <div className="fixed inset-0 pointer-events-none flex items-center justify-center z-30" style={{ top: '30%' }}>
          <div className="flex flex-col items-center gap-2 px-6 py-3 rounded-xl" style={{ background: 'rgba(0,0,0,0.75)', border: '1px solid rgba(212,175,55,0.3)', backdropFilter: 'blur(6px)' }}>
            <span className="text-yellow-400 font-black tracking-wider">Dealing Cards</span>
            <div className="flex gap-1.5">
              {[0,1,2].map(i => <div key={i} className="w-2 h-2 rounded-full bg-yellow-400 dealing-dot" style={{ animationDelay: `${i*0.2}s` }} />)}
            </div>
          </div>
        </div>
      )}

      {/* ── Action bar ── */}
      <div className="flex-shrink-0 px-4 py-3" style={{ background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(12px)', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
        <div className="max-w-2xl mx-auto">

          {/* WAITING phase */}
          {phase === 'waiting' && (
            <div className="flex flex-col items-center gap-3">
              <div className="flex items-center gap-2 text-white/50 text-sm">
                <span className="w-2 h-2 rounded-full bg-yellow-400 animate-pulse" />
                <span>Waiting for players… Share code <span className="text-yellow-400 font-black tracking-widest">{currentRoom.code}</span></span>
              </div>
              {isHost && (
                <button onClick={startGame} disabled={players.filter(p => !p.isBot).length < 1}
                  className="px-8 py-3 rounded-xl font-black text-black text-base transition-all active:scale-95"
                  style={{ background: 'linear-gradient(135deg,#d4af37,#f0c030)', boxShadow: '0 4px 20px rgba(212,175,55,0.4)' }}
                >
                  START GAME
                </button>
              )}
            </div>
          )}

          {/* DEALING phase */}
          {phase === 'dealing' && (
            <div className="flex justify-center">
              <span className="text-white/40 text-sm">Cards are being dealt…</span>
            </div>
          )}

          {/* BETTING phase */}
          {phase === 'betting' && (
            <div className="flex flex-wrap items-center justify-center gap-2">
              {!isLocalPlayerTurn ? (
                <div className="flex items-center gap-2 text-white/50">
                  <div className="w-4 h-4 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                  <span className="text-sm">Waiting for {players.find(p => p.isTurn)?.name ?? 'player'}…</span>
                </div>
              ) : (
                <>
                  <button onClick={handleFold} className="px-4 py-2.5 rounded-xl font-black text-sm transition-all active:scale-95"
                    style={{ background: 'linear-gradient(135deg,#991b1b,#7f1d1d)', border: '1px solid rgba(239,68,68,0.4)', color: '#fca5a5', boxShadow: '0 4px 12px rgba(153,27,27,0.4)' }}>
                    FOLD
                  </button>

                  {localPlayer?.status === 'blind' && (
                    <button onClick={handleSee} className="px-4 py-2.5 rounded-xl font-black text-sm transition-all active:scale-95"
                      style={{ background: 'linear-gradient(135deg,#1e40af,#1e3a8a)', border: '1px solid rgba(59,130,246,0.4)', color: '#93c5fd', boxShadow: '0 4px 12px rgba(30,64,175,0.4)' }}>
                      SEE CARDS
                    </button>
                  )}

                  {localPlayer?.status === 'blind' && (
                    <button onClick={playBlind} className="px-4 py-2.5 rounded-xl font-black text-sm transition-all active:scale-95"
                      style={{ background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', color: 'rgba(255,255,255,0.7)' }}>
                      PLAY BLIND ₹{currentRoom.currentBet}
                    </button>
                  )}

                  {localPlayer?.status === 'seen' && (
                    <button onClick={handleCall} className="px-4 py-2.5 rounded-xl font-black text-sm transition-all active:scale-95"
                      style={{ background: 'linear-gradient(135deg,#1e40af,#1e3a8a)', border: '1px solid rgba(59,130,246,0.4)', color: '#93c5fd', boxShadow: '0 4px 12px rgba(30,64,175,0.4)' }}>
                      CALL ₹{currentRoom.currentBet * 2}
                    </button>
                  )}

                  {/* Raise control */}
                  <div className="flex items-center gap-1 rounded-xl overflow-hidden" style={{ border: '1px solid rgba(255,255,255,0.12)', background: 'rgba(255,255,255,0.05)' }}>
                    <button onClick={() => setRaiseAmount(v => Math.max(currentRoom.currentBet * 2, v - currentRoom.minBet))} className="px-3 py-2.5 text-white/60 hover:text-yellow-400 font-black text-sm transition-colors">−</button>
                    <span className="text-white font-bold text-sm min-w-[60px] text-center">₹{raiseAmount}</span>
                    <button onClick={() => setRaiseAmount(v => Math.min(localPlayer?.balance ?? v, v + currentRoom.minBet))} className="px-3 py-2.5 text-white/60 hover:text-yellow-400 font-black text-sm transition-colors">+</button>
                  </div>

                  <button onClick={handleRaise} className="px-4 py-2.5 rounded-xl font-black text-sm transition-all active:scale-95"
                    style={{ background: 'linear-gradient(135deg,#d4af37,#b8860b)', border: '1px solid rgba(212,175,55,0.5)', color: '#000', boxShadow: '0 4px 16px rgba(212,175,55,0.35)' }}>
                    RAISE ₹{raiseAmount}
                  </button>

                  {localPlayer?.status === 'seen' && (
                    <button onClick={handleShow} className="px-4 py-2.5 rounded-xl font-black text-sm transition-all active:scale-95"
                      style={{ background: 'linear-gradient(135deg,#065f46,#064e3b)', border: '1px solid rgba(52,211,153,0.35)', color: '#6ee7b7', boxShadow: '0 4px 12px rgba(6,95,70,0.4)' }}>
                      SHOW
                    </button>
                  )}
                </>
              )}
            </div>
          )}

          {/* ROUND OVER / SHOWDOWN */}
          {(phase === 'round_over' || phase === 'showdown') && (
            <div className="flex justify-center">
              <span className="text-yellow-400/60 text-sm font-semibold">Next round starting automatically…</span>
            </div>
          )}
        </div>
      </div>

      {/* ── Leave confirm ── */}
      {showLeave && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.8)', backdropFilter: 'blur(4px)' }}>
          <div className="w-full max-w-sm rounded-2xl p-6 scale-in" style={{ background: 'linear-gradient(135deg,#1a0d3a,#100820)', border: '1px solid rgba(212,175,55,0.3)', boxShadow: '0 30px 80px rgba(0,0,0,0.7)' }}>
            <h3 className="text-white text-lg font-bold mb-2">Leave the Table?</h3>
            <p className="text-white/50 text-sm mb-6">Your current bet will be forfeited.</p>
            <div className="flex gap-3">
              <button onClick={() => setShowLeave(false)} className="flex-1 py-3 rounded-xl text-white/60 hover:text-white font-semibold transition-colors" style={{ border: '1px solid rgba(255,255,255,0.1)' }}>Stay</button>
              <button onClick={() => { leaveRoom(); navigate('/lobby'); }} className="flex-1 py-3 rounded-xl font-bold text-white transition-all active:scale-95" style={{ background: 'linear-gradient(135deg,#991b1b,#7f1d1d)', border: '1px solid rgba(239,68,68,0.3)' }}>Leave</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default GameRoom;
