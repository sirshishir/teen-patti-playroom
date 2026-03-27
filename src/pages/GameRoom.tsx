import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useGame, GamePlayer, Card, evaluateHand } from '@/contexts/GameContext';
import { useAuth } from '@/contexts/AuthContext';
import { useToast } from '@/hooks/use-toast';

// ─── Helpers ─────────────────────────────────────────────────────────────────
const SUIT_SYM: Record<string, string> = { hearts: '♥', diamonds: '♦', clubs: '♣', spades: '♠' };
const IS_RED = (s: string) => s === 'hearts' || s === 'diamonds';
const cardLabel = (v: number) => v === 1 ? 'A' : v === 11 ? 'J' : v === 12 ? 'Q' : v === 13 ? 'K' : String(v);

// ─── PlayingCard ──────────────────────────────────────────────────────────────
interface CardProps { card?: Card; faceDown?: boolean; delay?: number; animate?: boolean; size?: 'sm' | 'md' | 'lg'; }

const PlayingCard: React.FC<CardProps> = ({ card, faceDown = false, delay = 0, animate = false, size = 'md' }) => {
  const [visible, setVisible] = useState(false);
  const [flipped, setFlipped] = useState(false);

  useEffect(() => {
    if (!animate) { setVisible(false); return; }
    const t = setTimeout(() => setVisible(true), delay);
    return () => clearTimeout(t);
  }, [animate, delay]);

  useEffect(() => {
    if (visible && !faceDown) { const t = setTimeout(() => setFlipped(true), 350); return () => clearTimeout(t); }
    if (faceDown) setFlipped(false);
  }, [visible, faceDown]);

  const W = size === 'lg' ? 56 : size === 'sm' ? 30 : 42;
  const H = size === 'lg' ? 80 : size === 'sm' ? 43 : 60;

  return (
    <div
      style={{ width: W, height: H, flexShrink: 0, perspective: 600 }}
      className={`transition-all duration-500 ${visible ? 'opacity-100 scale-100 translate-y-0' : 'opacity-0 scale-75 -translate-y-4'}`}
    >
      <div style={{ width: '100%', height: '100%', transformStyle: 'preserve-3d', transition: 'transform 0.4s ease', transform: flipped ? 'rotateY(180deg)' : 'rotateY(0deg)', position: 'relative' }}>
        {/* Back */}
        <div className="absolute inset-0 rounded-md shadow-xl overflow-hidden" style={{ backfaceVisibility: 'hidden', WebkitBackfaceVisibility: 'hidden' }}>
          <div className="w-full h-full flex items-center justify-center" style={{ background: 'linear-gradient(135deg,#1a3a8f,#0d2260)', border: '1.5px solid rgba(255,255,255,0.18)', borderRadius: 6 }}>
            <div style={{ width: '80%', height: '80%', border: '1px solid rgba(100,149,237,0.3)', borderRadius: 3, backgroundImage: 'repeating-linear-gradient(45deg,rgba(255,255,255,0.04) 0px,rgba(255,255,255,0.04) 1px,transparent 1px,transparent 6px)' }} />
          </div>
        </div>
        {/* Front */}
        <div className="absolute inset-0 rounded-md shadow-xl bg-white overflow-hidden" style={{ backfaceVisibility: 'hidden', WebkitBackfaceVisibility: 'hidden', transform: 'rotateY(180deg)', border: '1px solid #e5e7eb' }}>
          {card && (
            <div className="w-full h-full flex flex-col" style={{ color: IS_RED(card.suit) ? '#dc2626' : '#111', padding: size === 'sm' ? 2 : 4 }}>
              <div style={{ lineHeight: 1 }}>
                <div style={{ fontWeight: 800, fontSize: size === 'sm' ? 8 : size === 'lg' ? 13 : 10 }}>{cardLabel(card.value)}</div>
                <div style={{ fontSize: size === 'sm' ? 7 : size === 'lg' ? 11 : 9 }}>{SUIT_SYM[card.suit]}</div>
              </div>
              <div className="flex-1 flex items-center justify-center" style={{ fontSize: size === 'sm' ? 14 : size === 'lg' ? 28 : 20 }}>{SUIT_SYM[card.suit]}</div>
              <div style={{ lineHeight: 1, alignSelf: 'flex-end', transform: 'rotate(180deg)' }}>
                <div style={{ fontWeight: 800, fontSize: size === 'sm' ? 8 : size === 'lg' ? 13 : 10 }}>{cardLabel(card.value)}</div>
                <div style={{ fontSize: size === 'sm' ? 7 : size === 'lg' ? 11 : 9 }}>{SUIT_SYM[card.suit]}</div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// ─── Chip ─────────────────────────────────────────────────────────────────────
const Chip: React.FC<{ amount: number }> = ({ amount }) => (
  <div className="flex items-center gap-1 rounded-full px-1.5 py-0.5" style={{ background: 'rgba(0,0,0,0.6)', border: '1px solid rgba(212,175,55,0.4)' }}>
    <div className="w-2.5 h-2.5 rounded-full bg-yellow-400 border border-yellow-600 flex-shrink-0" />
    <span className="text-yellow-300 font-bold" style={{ fontSize: 10 }}>₹{amount.toLocaleString()}</span>
  </div>
);

// ─── Status pill ──────────────────────────────────────────────────────────────
const StatusPill: React.FC<{ status: string }> = ({ status }) => {
  const cfg: Record<string, { label: string; color: string; bg: string }> = {
    blind:   { label: 'BLIND',  color: '#93c5fd', bg: 'rgba(30,64,175,0.5)' },
    seen:    { label: 'SEEN',   color: '#86efac', bg: 'rgba(22,101,52,0.5)' },
    folded:  { label: 'FOLD',   color: '#fca5a5', bg: 'rgba(153,27,27,0.5)' },
    all_in:  { label: 'ALL IN', color: '#fde68a', bg: 'rgba(120,53,15,0.6)' },
    waiting: { label: 'WAIT',   color: '#d1d5db', bg: 'rgba(75,85,99,0.4)'  },
  };
  const c = cfg[status] || cfg.waiting;
  return <span style={{ color: c.color, background: c.bg, fontSize: 8, fontWeight: 700, padding: '1px 5px', borderRadius: 99 }}>{c.label}</span>;
};

// ─── Opponent card (compact, horizontal) ─────────────────────────────────────
const OpponentSeat: React.FC<{ player: GamePlayer; animate: boolean; dealOffset: number }> = ({ player, animate, dealOffset }) => {
  const folded = player.status === 'folded';
  return (
    <div className={`flex flex-col items-center gap-1 transition-opacity duration-500 ${folded ? 'opacity-30' : ''}`} style={{ minWidth: 72 }}>
      {/* Face-down cards */}
      <div className="flex gap-0.5">
        {player.cards.length > 0
          ? player.cards.map((_, i) => <PlayingCard key={i} faceDown animate={animate} delay={dealOffset + i * 300} size="sm" />)
          : [0,1,2].map(i => <div key={i} className="rounded-sm bg-white/5 border border-white/10" style={{ width: 30, height: 43 }} />)
        }
      </div>

      {/* Info */}
      <div
        className={`flex flex-col items-center gap-0.5 rounded-xl px-2 py-1.5 ${player.isTurn ? 'turn-glow' : ''}`}
        style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(8px)', border: player.isTurn ? '1px solid rgba(250,204,21,0.8)' : '1px solid rgba(255,255,255,0.1)' }}
      >
        <div className="relative rounded-full overflow-hidden" style={{ width: 32, height: 32, border: player.isTurn ? '2px solid #facc15' : '2px solid rgba(255,255,255,0.2)' }}>
          <img src={player.photoURL} alt={player.name} className="w-full h-full object-cover" />
          {player.isTurn && <div className="absolute inset-0 bg-yellow-400/15 animate-pulse" />}
        </div>
        <span className="text-white font-semibold truncate" style={{ fontSize: 10, maxWidth: 64 }}>{player.name}</span>
        <Chip amount={player.balance} />
        <div className="flex items-center gap-1">
          <StatusPill status={player.status} />
          {player.isDealer && <span className="w-3.5 h-3.5 rounded-full bg-white text-black flex items-center justify-center font-black" style={{ fontSize: 8 }}>D</span>}
        </div>
        {player.currentBet > 0 && <span className="text-yellow-300 font-bold" style={{ fontSize: 9 }}>Bet ₹{player.currentBet}</span>}
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
  const [animate, setAnimate] = useState(false);
  const [localRevealed, setLocalRevealed] = useState(false);
  const [codeCopied, setCodeCopied] = useState(false);
  const prevPhase = useRef('');

  useEffect(() => {
    if (!currentRoom) { navigate('/lobby'); return; }
    setRaiseAmount(currentRoom.minBet * 2);
  }, []);

  useEffect(() => {
    if (!currentRoom) return;
    const phase = currentRoom.phase;
    if (phase === 'dealing' && prevPhase.current !== 'dealing') {
      setAnimate(true);
      setLocalRevealed(false);
    }
    if (phase === 'betting' && prevPhase.current === 'dealing') {
      setTimeout(() => setLocalRevealed(true), 700);
    }
    if (phase === 'waiting') {
      setAnimate(false);
      setLocalRevealed(false);
    }
    prevPhase.current = phase;
  }, [currentRoom?.phase]);

  if (!currentRoom) return null;

  const phase = currentRoom.phase;
  const opponents = currentRoom.players.filter(p => p.id !== localPlayerId);
  const isHost = currentRoom.players[0]?.id === localPlayerId;
  const handEval = localRevealed && localPlayer?.cards.length === 3 ? evaluateHand(localPlayer.cards) : null;

  const handleCopyCode = () => {
    navigator.clipboard.writeText(currentRoom.code).catch(() => {});
    setCodeCopied(true);
    setTimeout(() => setCodeCopied(false), 2000);
    toast({ title: `Code ${currentRoom.code} copied!` });
  };

  const handleSee = () => { seeCards(); setLocalRevealed(true); };
  const handleFold = () => { foldHand(); toast({ title: 'You folded.' }); };
  const handleCall = () => { callBet(); toast({ title: `Called ₹${currentRoom.currentBet * 2}` }); };
  const handleRaise = () => { raiseBet(raiseAmount); toast({ title: `Raised to ₹${raiseAmount}` }); };

  // Dealing delay: round-robin seat order
  const dealDelay = (seatIdx: number, cardIdx = 0) => (cardIdx * currentRoom.players.length + seatIdx) * 320;

  return (
    <div className="h-screen flex flex-col select-none overflow-hidden" style={{ background: 'radial-gradient(ellipse at 50% 20%,#1a0d3a,#0a0618 70%,#000)' }}>
      {/* Gold line */}
      <div className="h-0.5 flex-shrink-0" style={{ background: 'linear-gradient(90deg,transparent,#d4af37,#f0d060,#d4af37,transparent)' }} />

      {/* ── Header ── */}
      <header className="flex items-center justify-between px-3 py-2 flex-shrink-0" style={{ background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(10px)', borderBottom: '1px solid rgba(212,175,55,0.12)' }}>
        <span className="text-white/70 text-sm font-semibold truncate max-w-[90px]">{currentRoom.name}</span>

        <button onClick={handleCopyCode} className="flex items-center gap-1 px-2.5 py-1 rounded-lg" style={{ background: 'rgba(212,175,55,0.1)', border: '1px solid rgba(212,175,55,0.35)' }}>
          <span className="text-yellow-400 font-black tracking-widest text-xs">{currentRoom.code}</span>
          <span className="text-yellow-600 text-xs">{codeCopied ? '✓' : '📋'}</span>
        </button>

        <div className="flex items-center gap-2">
          <Chip amount={localPlayer?.balance ?? user?.balance ?? 0} />
          <button onClick={() => setShowLeave(true)} className="px-2.5 py-1 rounded-lg text-xs font-bold text-white/80" style={{ background: 'rgba(185,28,28,0.35)', border: '1px solid rgba(185,28,28,0.4)' }}>
            Leave
          </button>
        </div>
      </header>

      {/* ── Scrollable game area ── */}
      <div className="flex-1 flex flex-col min-h-0 overflow-hidden">

        {/* ── Opponents ── */}
        <div className="flex-shrink-0 px-2 pt-2 pb-1">
          <div className="flex justify-center gap-2 flex-wrap">
            {opponents.map((opp) => (
              <OpponentSeat
                key={opp.id}
                player={opp}
                animate={animate}
                dealOffset={dealDelay(opp.seatIndex)}
              />
            ))}
          </div>
        </div>

        {/* ── Oval table ── */}
        <div className="flex-shrink-0 flex justify-center px-4 py-1">
          <div
            className="relative table-felt flex items-center justify-center w-full"
            style={{
              maxWidth: 380,
              height: 110,
              borderRadius: '50%',
              border: '14px solid #4a2200',
              boxShadow: '0 0 0 2px #7a4810,0 0 0 4px #3d1a00,inset 0 0 40px rgba(0,0,0,0.5),0 15px 40px rgba(0,0,0,0.7)',
            }}
          >
            <div className="absolute inset-1.5 rounded-[50%] pointer-events-none" style={{ border: '1px solid rgba(212,175,55,0.18)' }} />

            <div className="flex flex-col items-center gap-1 z-10 px-4">
              {/* Pot */}
              <div className="flex items-center gap-1.5 rounded-full px-3 py-1 pot-pulse" style={{ background: 'rgba(0,0,0,0.65)', border: '1px solid rgba(212,175,55,0.4)', backdropFilter: 'blur(4px)' }}>
                <div className="flex">
                  {['#e53e3e','#d4af37','#3182ce'].map((c,i) => (
                    <div key={i} className="w-4 h-4 rounded-full border" style={{ background: c, borderColor: c, marginLeft: i > 0 ? -5 : 0, zIndex: 3-i }} />
                  ))}
                </div>
                <span className="text-yellow-300 font-bold" style={{ fontSize: 12 }}>POT ₹{currentRoom.pot.toLocaleString()}</span>
              </div>

              {/* Log (last 2 lines) */}
              <div className="flex flex-col items-center">
                {currentRoom.log.slice(-2).map((e, i) => (
                  <span key={i} className="text-white/35 text-center truncate max-w-[200px]" style={{ fontSize: 8 }}>{e}</span>
                ))}
              </div>
              {phase === 'betting' && (
                <span className="text-white/25" style={{ fontSize: 8 }}>Round {currentRoom.roundNumber} · Bet ₹{currentRoom.currentBet}</span>
              )}
            </div>

            {/* Dealer button */}
            <div className="absolute right-[8%] top-1/2 -translate-y-1/2 w-5 h-5 rounded-full flex items-center justify-center font-black" style={{ background: 'white', border: '1.5px solid #d4af37', color: '#111', fontSize: 8 }}>D</div>

            {/* Deck during dealing */}
            {phase === 'dealing' && (
              <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-20 pointer-events-none">
                {[0,1,2].map(i => (
                  <div key={i} className="absolute rounded-md" style={{ width: 28, height: 40, background: 'linear-gradient(135deg,#1a3a8f,#0d2260)', border: '1px solid rgba(255,255,255,0.2)', top: -i, left: -i*0.5, boxShadow: '0 2px 8px rgba(0,0,0,0.5)' }} />
                ))}
              </div>
            )}
          </div>
        </div>

        {/* ── User area ── */}
        <div className="flex-shrink-0 flex flex-col items-center gap-2 px-4 py-1">
          {/* User cards */}
          <div className="flex gap-2">
            {localPlayer?.cards.length
              ? localPlayer.cards.map((card, i) => (
                  <PlayingCard key={i} card={card} faceDown={!localRevealed} animate={animate} delay={dealDelay(0, i)} size="lg" />
                ))
              : [0,1,2].map(i => <div key={i} className="rounded-md bg-white/5 border border-white/10" style={{ width: 56, height: 80 }} />)
            }
          </div>

          {/* Hand rank */}
          {handEval && (
            <div className="px-3 py-0.5 rounded-full font-black tracking-wider" style={{ background: 'rgba(212,175,55,0.15)', color: '#fbbf24', border: '1px solid rgba(212,175,55,0.35)', fontSize: 10 }}>
              {handEval.label.toUpperCase()}
            </div>
          )}

          {/* User info bar */}
          <div className="flex items-center gap-2 rounded-xl px-3 py-2" style={{ background: 'rgba(0,0,0,0.65)', border: `1px solid ${localPlayer?.isTurn ? 'rgba(250,204,21,0.7)' : 'rgba(212,175,55,0.25)'}`, backdropFilter: 'blur(8px)', boxShadow: localPlayer?.isTurn ? '0 0 16px rgba(250,204,21,0.25)' : undefined }}>
            <div className="rounded-full overflow-hidden flex-shrink-0" style={{ width: 36, height: 36, border: '2px solid #d4af37' }}>
              <img src={localPlayer?.photoURL || user?.photoURL} alt="You" className="w-full h-full object-cover" />
            </div>
            <div>
              <p className="text-white font-bold" style={{ fontSize: 12 }}>{localPlayer?.name || user?.name || 'You'}</p>
              <Chip amount={localPlayer?.balance ?? user?.balance ?? 0} />
            </div>
            <div className="ml-1">
              {localPlayer && <StatusPill status={localPlayer.status} />}
              {localPlayer?.isDealer && <span className="ml-1 w-4 h-4 rounded-full bg-white text-black inline-flex items-center justify-center font-black" style={{ fontSize: 8 }}>D</span>}
            </div>
            {localPlayer && localPlayer.currentBet > 0 && (
              <span className="text-yellow-300 font-bold ml-1" style={{ fontSize: 10 }}>Bet ₹{localPlayer.currentBet}</span>
            )}
          </div>
        </div>

        {/* ── Action bar ── */}
        <div className="flex-shrink-0 mt-auto px-3 py-2" style={{ background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(12px)', borderTop: '1px solid rgba(255,255,255,0.06)' }}>

          {/* WAITING */}
          {phase === 'waiting' && (
            <div className="flex flex-col items-center gap-2">
              <p className="text-white/50 text-xs text-center">Share code <span className="text-yellow-400 font-black tracking-widest">{currentRoom.code}</span> with friends</p>
              {isHost && (
                <button onClick={startGame} className="w-full max-w-xs py-3 rounded-xl font-black text-black text-base active:scale-95 transition-all" style={{ background: 'linear-gradient(135deg,#d4af37,#f0c030)', boxShadow: '0 4px 20px rgba(212,175,55,0.4)' }}>
                  START GAME
                </button>
              )}
            </div>
          )}

          {/* DEALING */}
          {phase === 'dealing' && (
            <div className="flex items-center justify-center gap-2 py-1">
              <span className="text-white/40 text-sm">Dealing</span>
              {[0,1,2].map(i => <div key={i} className="w-1.5 h-1.5 rounded-full bg-yellow-400 dealing-dot" style={{ animationDelay: `${i*0.2}s` }} />)}
            </div>
          )}

          {/* BETTING */}
          {phase === 'betting' && (
            <div className="flex flex-col gap-2">
              {!isLocalPlayerTurn ? (
                <div className="flex items-center justify-center gap-2 py-1">
                  <div className="w-3.5 h-3.5 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                  <span className="text-white/50 text-xs">Waiting for {currentRoom.players.find(p => p.isTurn)?.name ?? 'player'}…</span>
                </div>
              ) : (
                <>
                  {/* Top row: main actions */}
                  <div className="flex items-center justify-center gap-2 flex-wrap">
                    <button onClick={handleFold} className="flex-1 min-w-[70px] py-2.5 rounded-xl font-black text-xs active:scale-95 transition-all"
                      style={{ background: 'linear-gradient(135deg,#991b1b,#7f1d1d)', border: '1px solid rgba(239,68,68,0.4)', color: '#fca5a5' }}>
                      FOLD
                    </button>

                    {localPlayer?.status === 'blind' && (
                      <button onClick={handleSee} className="flex-1 min-w-[80px] py-2.5 rounded-xl font-black text-xs active:scale-95 transition-all"
                        style={{ background: 'linear-gradient(135deg,#1e40af,#1e3a8a)', border: '1px solid rgba(59,130,246,0.4)', color: '#93c5fd' }}>
                        SEE CARDS
                      </button>
                    )}
                    {localPlayer?.status === 'blind' && (
                      <button onClick={playBlind} className="flex-1 min-w-[90px] py-2.5 rounded-xl font-black text-xs active:scale-95 transition-all"
                        style={{ background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', color: 'rgba(255,255,255,0.75)' }}>
                        PLAY BLIND ₹{currentRoom.currentBet}
                      </button>
                    )}
                    {localPlayer?.status === 'seen' && (
                      <button onClick={handleCall} className="flex-1 min-w-[80px] py-2.5 rounded-xl font-black text-xs active:scale-95 transition-all"
                        style={{ background: 'linear-gradient(135deg,#1e40af,#1e3a8a)', border: '1px solid rgba(59,130,246,0.4)', color: '#93c5fd' }}>
                        CALL ₹{currentRoom.currentBet * 2}
                      </button>
                    )}
                    {localPlayer?.status === 'seen' && (
                      <button onClick={showCardsAction} className="flex-1 min-w-[60px] py-2.5 rounded-xl font-black text-xs active:scale-95 transition-all"
                        style={{ background: 'linear-gradient(135deg,#065f46,#064e3b)', border: '1px solid rgba(52,211,153,0.35)', color: '#6ee7b7' }}>
                        SHOW
                      </button>
                    )}
                  </div>

                  {/* Raise row */}
                  <div className="flex items-center gap-2">
                    <button onClick={() => setRaiseAmount(v => Math.max(currentRoom.currentBet * 2, v - currentRoom.minBet))} className="w-8 h-8 rounded-lg flex items-center justify-center font-black text-white/60 hover:text-yellow-400 transition-colors" style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)' }}>−</button>
                    <span className="flex-1 text-center text-white font-bold text-sm">₹{raiseAmount}</span>
                    <button onClick={() => setRaiseAmount(v => Math.min(localPlayer?.balance ?? v, v + currentRoom.minBet))} className="w-8 h-8 rounded-lg flex items-center justify-center font-black text-white/60 hover:text-yellow-400 transition-colors" style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)' }}>+</button>
                    <button onClick={handleRaise} className="flex-1 py-2.5 rounded-xl font-black text-xs active:scale-95 transition-all"
                      style={{ background: 'linear-gradient(135deg,#d4af37,#b8860b)', border: '1px solid rgba(212,175,55,0.5)', color: '#000', boxShadow: '0 4px 12px rgba(212,175,55,0.3)' }}>
                      RAISE ₹{raiseAmount}
                    </button>
                  </div>
                </>
              )}
            </div>
          )}

          {/* ROUND OVER */}
          {(phase === 'round_over' || phase === 'showdown') && (
            <div className="flex justify-center py-1">
              <span className="text-yellow-400/60 text-xs font-semibold">Next round starting soon…</span>
            </div>
          )}
        </div>
      </div>

      {/* ── Winner overlay ── */}
      {phase === 'round_over' && currentRoom.winner && (
        <div className="fixed inset-0 z-40 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(6px)' }}>
          <div className="flex flex-col items-center gap-4 px-8 py-7 rounded-2xl w-full max-w-xs scale-in text-center" style={{ background: 'linear-gradient(135deg,#1a0d3a,#100820)', border: '1px solid rgba(212,175,55,0.4)', boxShadow: '0 0 60px rgba(212,175,55,0.15)' }}>
            <div className="text-yellow-400 font-black text-2xl">🏆 WINNER!</div>
            <img src={currentRoom.winner.photoURL} alt={currentRoom.winner.name} className="w-16 h-16 rounded-full border-2 border-yellow-400" />
            <div>
              <p className="text-white font-bold text-lg">{currentRoom.winner.name}</p>
              <p className="text-yellow-400 font-semibold text-sm">{currentRoom.winnerHand?.label}</p>
              <p className="text-green-400 font-bold text-lg mt-1">+₹{currentRoom.pot.toLocaleString()}</p>
            </div>
            <p className="text-white/30 text-xs">Next round in a moment…</p>
          </div>
        </div>
      )}

      {/* ── Leave confirm ── */}
      {showLeave && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.8)', backdropFilter: 'blur(4px)' }}>
          <div className="w-full max-w-xs rounded-2xl p-6 scale-in" style={{ background: 'linear-gradient(135deg,#1a0d3a,#100820)', border: '1px solid rgba(212,175,55,0.3)' }}>
            <h3 className="text-white text-lg font-bold mb-1">Leave the Table?</h3>
            <p className="text-white/50 text-sm mb-5">Your current bet will be forfeited.</p>
            <div className="flex gap-3">
              <button onClick={() => setShowLeave(false)} className="flex-1 py-3 rounded-xl text-white/60 font-semibold" style={{ border: '1px solid rgba(255,255,255,0.1)' }}>Stay</button>
              <button onClick={() => { leaveRoom(); navigate('/lobby'); }} className="flex-1 py-3 rounded-xl font-bold text-white active:scale-95 transition-all" style={{ background: 'linear-gradient(135deg,#991b1b,#7f1d1d)' }}>Leave</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default GameRoom;
